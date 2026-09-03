"""Real enrichment stage handlers, wired from v1 dependencies.

Each stage reads its input from the job and the persisted database, performs
external HTTP/model work OUTSIDE any transaction, and persists its output so a
later stage (or a re-run after a crash) can pick up where it left off. Stages
are idempotent and resumable: entity/source/document writes upsert, source
summaries and consensus are written as candidates, and publish atomically
promotes the candidate set.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .critiquebrainz import CRITIQUEBRAINZ_SOURCE, CritiqueBrainzAdapter
from .db import connect, seed
from .enrich import build_documents, corpus_from_documents
from .jobs import EnrichmentJob, JobStore, JobUnavailable, Stage, StageHandler
from .models import (
    ArtistEntity,
    IngestedContext,
    ReleaseEntity,
    ReviewSource,
    license_pool,
)
from .musicbrainz import MusicBrainzAdapter, resolve_release_group
from .providers import ChatResult
from .request import NowPlayingRequest
from .summarize import (
    StoredDocument,
    corpus_hash,
    publish,
    read_stored_documents,
    summarize,
    write_consensus_skipped,
    write_summary,
)
from .wikipedia import WIKIPEDIA_SOURCE, WikipediaAdapter


@dataclass
class PipelineDeps:
    """The live dependencies a stage handler uses (no held DB connection)."""

    store: JobStore
    musicbrainz: MusicBrainzAdapter
    critiquebrainz: CritiqueBrainzAdapter
    wikipedia: WikipediaAdapter
    model: str
    chat: Callable[[list[dict]], ChatResult]


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold()).strip("-") or "unknown"


def _release_slug(request: NowPlayingRequest) -> str:
    return f"{_slugify(request.artist)}-{_slugify(request.album)}"


def _first_release_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.match(r"(\d{4})", value)
    return int(match.group(1)) if match else None


def _request(job: EnrichmentJob) -> NowPlayingRequest:
    return NowPlayingRequest.model_validate(job.payload)


def _release_for(request: NowPlayingRequest, release_group) -> ReleaseEntity:
    return ReleaseEntity(
        id=_release_slug(request),
        title=release_group.title or request.album,
        artist_id=_slugify(request.artist),
        year=_first_release_year(release_group.first_release_date),
        artwork_url=release_group.artwork_url,
    )


# --- stage handlers -----------------------------------------------------------


def _resolve_entity(job: EnrichmentJob, lease_id: str, deps: PipelineDeps) -> bool:
    request = _request(job)
    key = request.lookup_key()
    result = resolve_release_group(key["artist"], key["album"], deps.musicbrainz)
    if result.status == "matched" and result.release_group is not None:
        deps.store.set_resolution(job.id, lease_id, result.release_group.mbid, "resolved")
        return True
    status = "unavailable" if result.status == "not-found" else "ambiguous"
    deps.store.set_resolution(job.id, lease_id, None, status)
    raise JobUnavailable(result.reason or "cannot resolve entity")


def _fetch_sources(job: EnrichmentJob, lease_id: str, deps: PipelineDeps) -> bool:
    mbid = job.resolved_release_group_id
    if not mbid:
        raise JobUnavailable("no resolved release group id")
    request = _request(job)
    # External HTTP, outside any database transaction.
    release_group = deps.musicbrainz.get_release_group(mbid)
    release = _release_for(request, release_group)
    artist = ArtistEntity(id=release.artist_id, name=request.artist)
    documents = build_documents(
        release_group, release, release.title, deps.critiquebrainz, deps.wikipedia
    )
    source_ids = {document.source_id for document in documents}
    sources: list[ReviewSource] = [
        source
        for source in (CRITIQUEBRAINZ_SOURCE, WIKIPEDIA_SOURCE)
        if source.id in source_ids
    ]
    context = IngestedContext(
        release=release, artist=artist, sources=sources, review_documents=documents
    )
    with connect(autocommit=False) as conn:
        seed(conn, context)
    deps.store.set_corpus_hash(
        job.id, lease_id, corpus_hash(corpus_from_documents(documents))
    )
    return True


def _group_by_source(documents: list[StoredDocument]) -> dict[str, list[StoredDocument]]:
    grouped: dict[str, list[StoredDocument]] = {}
    for document in documents:
        grouped.setdefault(document.source_id, []).append(document)
    return grouped


def _group_by_pool(documents: list[StoredDocument]) -> dict[str, list[StoredDocument]]:
    grouped: dict[str, list[StoredDocument]] = {}
    for document in documents:
        grouped.setdefault(license_pool(document.license_id), []).append(document)
    return grouped


def _existing_source_summaries(conn, release_slug: str) -> set[str]:
    rows = conn.execute(
        "SELECT source_id FROM public.summary_runs s "
        "JOIN public.releases r ON r.id = s.release_id "
        "WHERE r.slug = %s AND s.summary_kind = 'source' "
        "AND s.status IN ('candidate', 'published')",
        (release_slug,),
    ).fetchall()
    return {row[0] for row in rows if row[0]}


def _existing_consensus_pools(conn, release_slug: str) -> set[str]:
    rows = conn.execute(
        "SELECT license_pool FROM public.summary_runs s "
        "JOIN public.releases r ON r.id = s.release_id "
        "WHERE r.slug = %s AND s.summary_kind = 'consensus' "
        "AND s.status IN ('candidate', 'published')",
        (release_slug,),
    ).fetchall()
    return {row[0] for row in rows}


def _build_source_summaries(job: EnrichmentJob, lease_id: str, deps: PipelineDeps) -> bool:
    request = _request(job)
    slug = _release_slug(request)
    with connect() as conn:
        documents = read_stored_documents(conn, slug)
        done = _existing_source_summaries(conn, slug)
    if not documents:
        raise JobUnavailable("no persisted documents to summarize")
    by_source = _group_by_source(documents)
    for source_id, source_documents in by_source.items():
        if source_id in done:
            continue
        # One bounded model call per source, outside any transaction. Renew the
        # lease first so a long model call cannot be reaped mid-stage.
        first = source_documents[0]
        deps.store.renew(job.id, lease_id)
        summary = summarize(
            _as_corpus(source_documents),
            model=deps.model,
            chat=deps.chat,
            kind="source",
            license_pool=license_pool(first.license_id),
            license_url=first.license_url,
            source_id=source_id,
            attribution=_attribution(first),
        )
        with connect(autocommit=False) as conn:
            write_summary(conn, slug, summary, status="candidate")
        # A source summary is one bounded work unit; re-queue for the next one.
        deps.store.commit(job.id, lease_id, stage=job.stage, state="queued")
        return False
    return True


def _build_consensus(job: EnrichmentJob, lease_id: str, deps: PipelineDeps) -> bool:
    request = _request(job)
    slug = _release_slug(request)
    with connect() as conn:
        documents = read_stored_documents(conn, slug)
        done = _existing_consensus_pools(conn, slug)
    if not documents:
        raise JobUnavailable("no persisted documents for consensus")
    by_pool = _group_by_pool(documents)
    for pool, pool_documents in by_pool.items():
        if pool in done:
            continue
        distinct_sources = {d.source_id for d in pool_documents}
        first = pool_documents[0]
        attribution = _attribution(first)
        if len(distinct_sources) < 2:
            with connect(autocommit=False) as conn:
                write_consensus_skipped(
                    conn,
                    slug,
                    license_pool=pool,
                    license_url=first.license_url,
                    attribution=attribution,
                )
        else:
            # Renew the lease before the model call so it cannot be reaped.
            deps.store.renew(job.id, lease_id)
            consensus = summarize(
                _as_corpus(pool_documents),
                model=deps.model,
                chat=deps.chat,
                kind="consensus",
                license_pool=pool,
                license_url=first.license_url,
                attribution=attribution,
            )
            with connect(autocommit=False) as conn:
                write_summary(conn, slug, consensus, status="candidate")
        deps.store.commit(job.id, lease_id, stage=job.stage, state="queued")
        return False
    return True


def _publish(job: EnrichmentJob, lease_id: str, deps: PipelineDeps) -> bool:
    # Summaries are written atomically as candidates; publish validates the
    # candidate set exists and flips it to published, demoting the old set.
    request = _request(job)
    slug = _release_slug(request)
    with connect() as conn:
        candidates = conn.execute(
            "SELECT count(*) FROM public.summary_runs s "
            "JOIN public.releases r ON r.id = s.release_id "
            "WHERE r.slug = %s AND s.status = 'candidate'",
            (slug,),
        ).fetchone()[0]
    if not candidates:
        raise RuntimeError("no candidate summaries to publish")
    with connect(autocommit=False) as conn:
        publish(conn, slug)
    return True


def _attribution(document: StoredDocument) -> str:
    return f"{document.publication} — {document.license_id}"


def _as_corpus(documents: list[StoredDocument]):
    from .summarize import CorpusDocument

    return [
        CorpusDocument(id=document.id, text=document.content, kind="review")
        for document in documents
    ]


def build_handlers(deps: PipelineDeps) -> dict[Stage, StageHandler]:
    """The real five-stage handler map, constructed from live dependencies."""
    return {
        "resolve_entity": lambda job, lease_id: _resolve_entity(job, lease_id, deps),
        "fetch_sources": lambda job, lease_id: _fetch_sources(job, lease_id, deps),
        "build_source_summaries": lambda job, lease_id: _build_source_summaries(
            job, lease_id, deps
        ),
        "build_consensus": lambda job, lease_id: _build_consensus(job, lease_id, deps),
        "publish": lambda job, lease_id: _publish(job, lease_id, deps),
    }
