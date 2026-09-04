"""Compose the enrichment pipeline: entity resolution, source fetch, summarization.

This is the glue the worker's stage handlers call. It turns a resolved release
group into licensed review documents (CritiqueBrainz + Wikipedia Reception),
maps them to a summarizer corpus, and produces a provenance-checked summary.
"""

from __future__ import annotations

from .critiquebrainz import CritiqueBrainzAdapter
from .critiquebrainz import to_document as cb_document
from .entities import ReleaseGroup
from .models import Genre, ReleaseEntity, ReviewDocument, Summary, license_pool
from .summarize import CorpusDocument, summarize
from .wikipedia import WikipediaAdapter, normalize_article_title
from .wikipedia import to_document as wiki_document


def corpus_from_documents(documents: list[ReviewDocument]) -> list[CorpusDocument]:
    """Map stored review documents to the summarizer's corpus shape.

    The full body is the summarization input; it never becomes public.
    """
    return [
        CorpusDocument(
            id=document.id,
            text=document.content or document.public_excerpt,
            kind="review",
        )
        for document in documents
    ]


def pool_for_document(document: ReviewDocument) -> str:
    """The license-compatibility pool a document belongs to."""
    return license_pool(document.policy.license_id)


def group_by_pool(
    documents: list[ReviewDocument],
) -> dict[str, list[ReviewDocument]]:
    """Partition documents so each license pool is summarized separately."""
    grouped: dict[str, list[ReviewDocument]] = {}
    for document in documents:
        grouped.setdefault(pool_for_document(document), []).append(document)
    return grouped


def genres_from_release_group(release_group: ReleaseGroup) -> list[Genre]:
    """Return a short, deduplicated display list from MusicBrainz tags."""
    genres: list[Genre] = []
    seen: set[str] = set()
    for raw_tag in release_group.tags:
        tag = " ".join(raw_tag.split())
        key = tag.casefold()
        if not tag or key in seen:
            continue
        seen.add(key)
        genres.append(Genre(name=tag.title() if tag.islower() else tag, source_ids=[]))
        if len(genres) == 6:
            break
    return genres


def build_documents(
    release_group: ReleaseGroup,
    release: ReleaseEntity,
    article_title: str,
    critiquebrainz: CritiqueBrainzAdapter,
    wikipedia: WikipediaAdapter,
) -> list[ReviewDocument]:
    """Fetch licensed review documents for a resolved release group."""
    documents: list[ReviewDocument] = []
    for review in critiquebrainz.search_reviews(release_group.mbid):
        documents.append(cb_document(review, release))
    article_title = normalize_article_title(article_title)
    reception = wikipedia.reception_section(article_title, artist=release_group.artist)
    if reception is not None:
        documents.append(wiki_document(reception, release, article_title))
    return documents


def enrich_release(
    release: ReleaseEntity,
    release_group: ReleaseGroup,
    article_title: str,
    critiquebrainz: CritiqueBrainzAdapter,
    wikipedia: WikipediaAdapter,
    *,
    model: str,
    chat,
) -> dict[str, Summary]:
    """Fetch sources and summarize each license pool separately.

    Incompatible licenses are never merged into one corpus, so no claim can
    cite documents from two different pools. The result maps pool id (a license
    id) to that pool's validated summary.
    """
    documents = build_documents(release_group, release, article_title, critiquebrainz, wikipedia)
    summaries: dict[str, Summary] = {}
    for pool, pool_documents in group_by_pool(documents).items():
        summaries[pool] = summarize(corpus_from_documents(pool_documents), model=model, chat=chat)
    return summaries
