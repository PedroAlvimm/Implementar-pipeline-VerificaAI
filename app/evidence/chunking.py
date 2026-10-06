from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvidenceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    title: str
    url: str
    domain: str
    published_at: datetime | None
    independence_group: str


class EvidenceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    document_id: str
    index: int
    text: str
    source_title: str
    source_url: str
    source_domain: str
    published_at: datetime | None
    independence_group: str


def _boundary(text: str, start: int, maximum_end: int) -> int:
    if maximum_end >= len(text):
        return len(text)
    minimum = start + (maximum_end - start) // 2
    punctuation = max(text.rfind(mark, minimum, maximum_end) for mark in ".!?")
    if punctuation >= minimum:
        return punctuation + 1
    space = text.rfind(" ", minimum, maximum_end)
    return space if space > start else maximum_end


def chunk_document(
    document: EvidenceDocument,
    max_chars: int = 1_200,
    overlap_chars: int = 200,
) -> list[EvidenceChunk]:
    text = document.text.strip()
    if not text:
        return []
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("Limites de chunk inválidos")
    chunks: list[EvidenceChunk] = []
    start = 0
    while start < len(text):
        end = _boundary(text, start, min(len(text), start + max_chars))
        content = text[start:end].strip()
        digest = hashlib.sha256(f"{document.id}\0{len(chunks)}\0{content}".encode()).hexdigest()[
            :16
        ]
        chunks.append(
            EvidenceChunk(
                evidence_id=f"ev_{digest}",
                document_id=document.id,
                index=len(chunks),
                text=content,
                source_title=document.title,
                source_url=document.url,
                source_domain=document.domain,
                published_at=document.published_at,
                independence_group=document.independence_group,
            )
        )
        if end >= len(text):
            break
        next_start = max(start + 1, end - overlap_chars)
        while next_start > start and next_start < len(text) and text[next_start - 1].isalnum():
            next_start -= 1
        start = next_start
    return chunks
