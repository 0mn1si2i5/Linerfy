"""Compose the enrichment pipeline: entity resolution, source fetch, summarization.

This is the glue the worker's stage handlers call. It turns a resolved release
group into licensed review documents (CritiqueBrainz + Wikipedia Reception),
maps them to a summarizer corpus, and produces a provenance-checked summary.
"""

from __future__ import annotations

from .critiquebrainz import CritiqueBrainzAdapter
from .critiquebrainz import to_document as cb_document
from .entities import ReleaseGroup
from .models import ReleaseEntity, ReviewDocument, Summary
from .summarize import CorpusDocument, summarize
from .wikipedia import WikipediaAdapter
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
    reception = wikipedia.reception_section(article_title)
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
) -> Summary:
    """Fetch sources and summarize them into a validated ``Summary``."""
    documents = build_documents(
        release_group, release, article_title, critiquebrainz, wikipedia
    )
    corpus = corpus_from_documents(documents)
    return summarize(corpus, model=model, chat=chat)
