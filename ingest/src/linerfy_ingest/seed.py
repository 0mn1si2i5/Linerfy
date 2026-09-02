"""Normalize an IngestedContext into the row shapes of the Supabase catalog migration.

This is the single tested place where entity matching (release/artist), source
policies, review documents, excerpts, genres, and a traceable summary become
insertable rows. `db.py` executes these rows against a live database.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date

from .models import IngestedContext, ReviewDocument

_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def stable_uuid(kind: str, slug: str) -> str:
    """Deterministic uuid so a seed is idempotent and FKs resolve across tables."""
    return str(uuid.uuid5(_NAMESPACE, f"linerfy:{kind}:{slug}"))


def _fingerprint(document: ReviewDocument) -> str:
    fields = [
        document.source_url,
        document.title,
        document.author or "",
        document.published_at.isoformat() if document.published_at else "",
        document.public_excerpt,
    ]
    return hashlib.sha256("\n".join(fields).encode("utf-8")).hexdigest()


def _release_date(year: int | None) -> str | None:
    # The public contract exposes `year`; the DB stores a full `release_date`.
    # Year-only releases are stored as Jan 1 of that year.
    return date(year, 1, 1).isoformat() if year is not None else None


def to_rows(context: IngestedContext) -> dict[str, list[dict]]:
    """Return migration-shaped rows keyed by table name.

    Timestamps that the migration fills with `default now()` are omitted so the
    seed stays deterministic; the loader can rely on database defaults.
    """

    artist_id = stable_uuid("artist", context.artist.id)
    release_id = stable_uuid("release", context.release.id)

    artists = [
        {
            "id": artist_id,
            "slug": context.artist.id,
            "name": context.artist.name,
        }
    ]
    releases = [
        {
            "id": release_id,
            "slug": context.release.id,
            "artist_id": artist_id,
            "title": context.release.title,
            "release_date": _release_date(context.release.year),
            "artwork_url": context.release.artwork_url,
        }
    ]

    source_uuid = {
        source.id: stable_uuid("source", source.id) for source in context.sources
    }
    review_sources = [
        {
            "id": source_uuid[source.id],
            "slug": source.id,
            "publication": source.publication,
            "homepage_url": source.homepage_url,
        }
        for source in context.sources
    ]
    # Policy is source-level; the ingest contract still carries it per document,
    # so dedupe by source here (source_policies.source_id is the primary key).
    policy_by_source = {
        document.source_id: document.policy for document in context.review_documents
    }
    source_policies = [
        {
            "source_id": source_uuid[source.id],
            "crawl_allowed": policy_by_source[source.id].crawl_allowed,
            "requests_per_minute": policy_by_source[source.id].requests_per_minute,
            "retention_days": policy_by_source[source.id].retention_days,
            "excerpt_max_chars": policy_by_source[source.id].excerpt_max_chars,
            "attribution_required": policy_by_source[source.id].attribution_required,
            "removal_contact": policy_by_source[source.id].removal_contact,
        }
        for source in context.sources
    ]

    document_uuid = {
        document.id: stable_uuid("document", document.id)
        for document in context.review_documents
    }
    review_documents = [
        {
            "id": document_uuid[document.id],
            "slug": document.id,
            "release_id": release_id,
            "source_id": source_uuid[document.source_id],
            "source_url": document.source_url,
            "title": document.title,
            "author": document.author,
            "published_at": document.published_at.isoformat()
            if document.published_at
            else None,
            "score": document.score,
            "score_scale": document.score_scale,
            "content_fingerprint": _fingerprint(document),
            "status": "published",
        }
        for document in context.review_documents
    ]

    review_excerpts = [
        {
            "id": stable_uuid("excerpt", f"{document.id}"),
            "document_id": document_uuid[document.id],
            "excerpt": document.public_excerpt,
            # The fixture only carries paraphrases; verbatim quotations are not
            # yet distinguishable in the ingest contract.
            "is_paraphrase": True,
        }
        for document in context.review_documents
    ]

    summary_run_id = stable_uuid("summary", context.release.id)
    summary_runs = [
        {
            "id": summary_run_id,
            "release_id": release_id,
            "model": context.summary.model,
            "prompt_version": context.summary.prompt_version,
            "locale": context.summary.locale,
            "corpus_hash": context.summary.corpus_hash,
            "generated_at": context.summary.generated_at.isoformat(),
            "status": "published",
        }
    ]

    claims = []
    claim_sources = []
    for order, claim in enumerate(context.summary.claims):
        claim_id = stable_uuid("claim", f"{context.release.id}:{order}")
        claims.append(
            {
                "id": claim_id,
                "summary_run_id": summary_run_id,
                "claim_order": order,
                "claim_text": claim.text,
            }
        )
        claim_sources.extend(
            {
                "claim_id": claim_id,
                "document_id": document_uuid[source_id],
            }
            for source_id in claim.source_ids
        )

    genre_uuid = {
        genre.name: stable_uuid("genre", f"{context.release.id}:{genre.name}")
        for genre in context.genres
    }
    genres = [
        {
            "id": genre_uuid[genre.name],
            "release_id": release_id,
            "name": genre.name,
        }
        for genre in context.genres
    ]
    genre_sources = [
        {
            "genre_id": genre_uuid[genre.name],
            "document_id": document_uuid[source_id],
        }
        for genre in context.genres
        for source_id in genre.source_ids
    ]

    return {
        "artists": artists,
        "releases": releases,
        "genres": genres,
        "review_sources": review_sources,
        "source_policies": source_policies,
        "review_documents": review_documents,
        "review_excerpts": review_excerpts,
        "genre_sources": genre_sources,
        "summary_runs": summary_runs,
        "claims": claims,
        "claim_sources": claim_sources,
    }
