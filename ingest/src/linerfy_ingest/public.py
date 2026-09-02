"""Map an IngestedContext to the public MusicContext shape consumed by clients.

This is the delivery boundary. The ingest contract (snake_case, provenance
focused) and the public contract (camelCase, display shaped, validated by Zod in
`packages/domain`) are intentionally different objects; this module is the only
place that translates between them. The two sides agree on a shared JSON fixture
that Python produces and Zod re-validates.
"""

from __future__ import annotations

from datetime import datetime

from .models import IngestedContext


def _iso_z(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _omit_none(mapping: dict) -> dict:
    return {key: value for key, value in mapping.items() if value is not None}


def _publication_name(context: IngestedContext, source_id: str) -> str:
    for source in context.sources:
        if source.id == source_id:
            return source.publication
    raise ValueError(f"unknown source: {source_id}")


def to_public(context: IngestedContext) -> dict:
    sources = [
        _omit_none(
            {
                "id": document.id,
                "publication": _publication_name(context, document.source_id),
                "author": document.author,
                "title": document.title,
                "url": document.source_url,
                "publishedAt": document.published_at.isoformat()
                if document.published_at
                else None,
                "score": (
                    {"value": document.score, "scale": document.score_scale}
                    if document.score is not None and document.score_scale is not None
                    else None
                ),
            }
        )
        for document in context.review_documents
    ]

    excerpts = [
        {
            "id": f"{document.id}-excerpt",
            "sourceId": document.id,
            "text": document.public_excerpt,
            "kind": "paraphrase",
        }
        for document in context.review_documents
    ]

    claims = [
        {
            "id": f"claim-{order + 1}",
            "text": claim.text,
            "sourceIds": claim.source_ids,
        }
        for order, claim in enumerate(context.summary.claims)
    ]

    return {
        "artist": {"id": context.artist.id, "name": context.artist.name},
        "release": _omit_none(
            {
                "id": context.release.id,
                "title": context.release.title,
                "artistId": context.release.artist_id,
                "year": context.release.year,
                "artworkUrl": context.release.artwork_url,
            }
        ),
        "recordings": [],
        "genres": [
            {"name": genre.name, "sourceIds": genre.source_ids}
            for genre in context.genres
        ],
        "sources": sources,
        "excerpts": excerpts,
        "summary": {
            "locale": context.summary.locale,
            "corpusHash": context.summary.corpus_hash,
            "model": context.summary.model,
            "generatedAt": _iso_z(context.summary.generated_at),
            "claims": claims,
        },
    }
