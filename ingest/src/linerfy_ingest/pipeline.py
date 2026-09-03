"""Real enrichment stage handlers, wired from v1 dependencies.

Each stage reads its input from the job/database and persists its output so the
next stage (or a re-run after a crash) can pick up where it left off. Stages are
idempotent: entity/source/document writes upsert, and summaries replace
atomically. The model call is guarded by the caller's budget ledger and happens
outside any database transaction.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

import psycopg

from .critiquebrainz import CRITIQUEBRAINZ_SOURCE, CritiqueBrainzAdapter
from .db import seed
from .enrich import build_documents, corpus_from_documents, group_by_pool
from .jobs import EnrichmentJob, JobStore, JobUnavailable, Stage, StageHandler
from .models import ArtistEntity, IngestedContext, ReleaseEntity, ReviewSource
from .musicbrainz import MusicBrainzAdapter, resolve_release_group
from .providers import ChatResult
from .request import NowPlayingRequest
from .summarize import corpus_hash, summarize, write_summary
from .wikipedia import WIKIPEDIA_SOURCE, WikipediaAdapter


@dataclass
class PipelineDeps:
    """The real dependencies a stage handler uses."""

    store: JobStore
    conn: psycopg.Connection
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


def _resolve_entity(job: EnrichmentJob, deps: PipelineDeps) -> None:
    request = _request(job)
    key = request.lookup_key()
    result = resolve_release_group(key["artist"], key["album"], deps.musicbrainz)
    if result.status == "matched" and result.release_group is not None:
        deps.store.set_resolution(job, result.release_group.mbid, "resolved")
        return
    status = "unavailable" if result.status == "not-found" else "ambiguous"
    deps.store.set_resolution(job, None, status)
    raise JobUnavailable(result.reason or "cannot resolve entity")


def _fetch_sources(job: EnrichmentJob, deps: PipelineDeps) -> None:
    mbid = job.resolved_release_group_id
    if not mbid:
        raise JobUnavailable("no resolved release group id")
    request = _request(job)
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
    seed(deps.conn, context)
    deps.store.set_corpus_hash(job, corpus_hash(corpus_from_documents(documents)))


def _build_source_summaries(job: EnrichmentJob, deps: PipelineDeps) -> None:
    request = _request(job)
    slug = _release_slug(request)
    mbid = job.resolved_release_group_id
    if not mbid:
        raise JobUnavailable("no resolved release group id")
    release_group = deps.musicbrainz.get_release_group(mbid)
    release = _release_for(request, release_group)
    documents = build_documents(
        release_group, release, release.title, deps.critiquebrainz, deps.wikipedia
    )
    for pool, pool_documents in group_by_pool(documents).items():
        summary = summarize(
            corpus_from_documents(pool_documents), model=deps.model, chat=deps.chat
        )
        write_summary(deps.conn, slug, summary, pool=pool)


def _build_consensus(job: EnrichmentJob, deps: PipelineDeps) -> None:
    # v1 has at most one source per license pool, so there is nothing to
    # reconcile across sources. This stage is a documented no-op that keeps the
    # five-stage shape; consensus would only run for a pool with >=2 sources.
    return


def _publish(job: EnrichmentJob, deps: PipelineDeps) -> None:
    # Summaries are written atomically as published by write_summary. Publish
    # verifies the release actually has a published summary before finalizing
    # the job; anything else raises so the job is retried rather than marked
    # ready with an empty context.
    request = _request(job)
    slug = _release_slug(request)
    rows = deps.conn.execute(
        "SELECT count(*) FROM public.summary_runs s "
        "JOIN public.releases r ON r.id = s.release_id "
        "WHERE r.slug = %s AND s.status = 'published'",
        (slug,),
    ).fetchone()
    if not rows or rows[0] == 0:
        raise RuntimeError("no published summary to finalize")


def build_handlers(deps: PipelineDeps) -> dict[Stage, StageHandler]:
    """The real five-stage handler map, constructed from live dependencies."""
    return {
        "resolve_entity": lambda job: _resolve_entity(job, deps),
        "fetch_sources": lambda job: _fetch_sources(job, deps),
        "build_source_summaries": lambda job: _build_source_summaries(job, deps),
        "build_consensus": lambda job: _build_consensus(job, deps),
        "publish": lambda job: _publish(job, deps),
    }
