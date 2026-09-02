"""Generate a traceable Chinese summary from a corpus of review documents.

The summarizer is corpus-agnostic: it takes a list of documents (professional
reviews, community posts, ...), each labelled with an id and a kind, and asks a
model to produce concise Chinese claims that each cite the documents supporting
them. Only the corpus text is ever read here; the full text is never public.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .models import CitedClaim, Summary
from .seed import stable_uuid

_DEFAULT_BASE_URL = "https://api.deepseek.com"
_DEFAULT_MODEL = "deepseek-chat"


@dataclass(frozen=True)
class CorpusDocument:
    id: str
    text: str
    kind: str = "review"


def corpus_hash(corpus: list[CorpusDocument]) -> str:
    """Deterministic fingerprint of the corpus, so a summary can be reproduced
    or invalidated when its material changes."""
    ordered = sorted(corpus, key=lambda document: document.id)
    payload = "\n".join(
        f"{document.id}\n{document.kind}\n{document.text}" for document in ordered
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_prompt(corpus: list[CorpusDocument]) -> str:
    materials = "\n\n".join(
        f"[id: {document.id}] (type: {document.kind})\n{document.text}"
        for document in corpus
    )
    return (
        "你是音乐乐评的中文整理助手。下面是若干篇关于同一张专辑的材料，"
        "每篇以 `[id]` 标注，`(type)` 说明来源类型（如 review 专业乐评、community 社区观点）。\n"
        "请基于这些材料写 3-5 条中文「共识/分歧」结论。要求：\n"
        "1. 只依据给定材料，不编造。\n"
        "2. 每条结论一句话左右，客观克制。\n"
        "3. source_ids 只能使用下面出现的 `[id]`，表示支撑该结论的来源。\n"
        "4. 只输出 JSON，不要任何其他文字，格式：\n"
        '{"claims": [{"text": "结论", "source_ids": ["id"]}]}\n\n'
        f"材料：\n{materials}"
    )


class _ClaimItem(BaseModel):
    text: str = Field(min_length=1)
    source_ids: list[str] = Field(min_length=1)


class _SummaryResponse(BaseModel):
    claims: list[_ClaimItem] = Field(min_length=1)


def _parse_claims(raw: str, corpus_ids: set[str]) -> list[CitedClaim]:
    """Parse the model's JSON and reject any claim citing an unknown source."""
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or start >= end:
        raise ValueError("model response is not JSON")
    response = _SummaryResponse.model_validate(json.loads(raw[start : end + 1]))
    claims: list[CitedClaim] = []
    for item in response.claims:
        unknown = set(item.source_ids) - corpus_ids
        if unknown:
            raise ValueError(f"claim cites unknown sources: {sorted(unknown)}")
        claims.append(CitedClaim(text=item.text, source_ids=item.source_ids))
    return claims


def _chat_completion(api_key: str, base_url: str, model: str, prompt: str) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def summarize(
    corpus: list[CorpusDocument],
    *,
    api_key: str,
    base_url: str = _DEFAULT_BASE_URL,
    model: str = _DEFAULT_MODEL,
    locale: str = "zh-CN",
    prompt_version: str = "summarize-v1",
    generated_at: datetime | None = None,
) -> Summary:
    if not corpus:
        raise ValueError("summarize requires a non-empty corpus")
    if not api_key:
        raise ValueError("MODEL_API_KEY is required")
    raw = _chat_completion(api_key, base_url, model, _build_prompt(corpus))
    claims = _parse_claims(raw, {document.id for document in corpus})
    return Summary(
        locale=locale,
        model=model,
        prompt_version=prompt_version,
        generated_at=generated_at or datetime.now(UTC),
        corpus_hash=corpus_hash(corpus),
        claims=claims,
    )


def read_corpus(conn, release_slug: str) -> list[CorpusDocument]:
    """Read a release's published document bodies into a summarizer corpus."""
    release_id = uuid.UUID(stable_uuid("release", release_slug))
    rows = conn.execute(
        "SELECT d.slug, b.content FROM public.review_documents d "
        "JOIN public.review_document_bodies b ON b.document_id = d.id "
        "WHERE d.release_id = %s AND d.status = 'published'",
        (release_id,),
    ).fetchall()
    return [CorpusDocument(id=slug, text=content) for slug, content in rows]


def write_summary(conn, release_slug: str, summary: Summary) -> int:
    """Write the summary run + claims + citations, upserting over any prior run."""
    release_id = uuid.UUID(stable_uuid("release", release_slug))
    summary_run_id = uuid.UUID(stable_uuid("summary", release_slug))
    written = 0

    cursor = conn.execute(
        "INSERT INTO public.summary_runs "
        "(id, release_id, model, prompt_version, locale, corpus_hash, generated_at, status) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (id) DO UPDATE SET model=EXCLUDED.model, "
        "prompt_version=EXCLUDED.prompt_version, locale=EXCLUDED.locale, "
        "corpus_hash=EXCLUDED.corpus_hash, generated_at=EXCLUDED.generated_at, "
        "status=EXCLUDED.status",
        (
            summary_run_id,
            release_id,
            summary.model,
            summary.prompt_version,
            summary.locale,
            summary.corpus_hash,
            summary.generated_at,
            "published",
        ),
    )
    written += cursor.rowcount

    # Replace any prior run's claims in full (cascades to claim_sources), so a
    # re-summary with a different number of claims cannot leave stale ones behind.
    cursor = conn.execute(
        "DELETE FROM public.claims WHERE summary_run_id = %s", (summary_run_id,)
    )
    written += cursor.rowcount

    for order, claim in enumerate(summary.claims):
        claim_id = uuid.UUID(stable_uuid("claim", f"{release_slug}:{order}"))
        cursor = conn.execute(
            "INSERT INTO public.claims (id, summary_run_id, claim_order, claim_text) "
            "VALUES (%s,%s,%s,%s) "
            "ON CONFLICT (id) DO UPDATE SET claim_order=EXCLUDED.claim_order, "
            "claim_text=EXCLUDED.claim_text",
            (claim_id, summary_run_id, order, claim.text),
        )
        written += cursor.rowcount
        for source_id in claim.source_ids:
            document_id = uuid.UUID(stable_uuid("document", source_id))
            cursor = conn.execute(
                "INSERT INTO public.claim_sources (claim_id, document_id) "
                "VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (claim_id, document_id),
            )
            written += cursor.rowcount

    return written
