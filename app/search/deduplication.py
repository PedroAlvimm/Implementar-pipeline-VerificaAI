from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from app.search.canonical import canonicalize_url

_WORDS = re.compile(r"\w+", re.UNICODE)


class DocumentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    url: str
    title: str
    text: str
    original_source: str | None = None
    independence_group: str | None = None


@dataclass(frozen=True)
class GroupingResult:
    documents: list[DocumentCandidate]
    reasons: dict[str, str]


def _normalized_words(text: str) -> set[str]:
    return {word.casefold() for word in _WORDS.findall(text)}


def _similarity(left: str, right: str) -> float:
    left_words = _normalized_words(left)
    right_words = _normalized_words(right)
    union = left_words | right_words
    return len(left_words & right_words) / len(union) if union else 0.0


def _group_id(seed: str) -> str:
    return f"grp_{hashlib.sha256(seed.encode()).hexdigest()[:12]}"


def group_document_independence(
    documents: list[DocumentCandidate],
) -> GroupingResult:
    assigned: list[DocumentCandidate] = []
    reasons: dict[str, str] = {}
    canonical_to_group: dict[str, str] = {}
    exact_to_group: dict[str, str] = {}

    for document in documents:
        canonical = canonicalize_url(document.url)
        normalized_content = " ".join(sorted(_normalized_words(document.text))).encode()
        content_hash = hashlib.sha256(normalized_content).hexdigest()
        group: str | None = None
        reason = "unique_source"
        if document.original_source:
            group = canonical_to_group.get(canonicalize_url(document.original_source))
            if group:
                reason = "declared_original_source"
        if group is None and content_hash in exact_to_group:
            group = exact_to_group[content_hash]
            reason = "exact_content_hash"
        if group is None:
            for previous in assigned:
                if _similarity(document.text, previous.text) >= 0.70:
                    group = previous.independence_group
                    reason = "near_duplicate_content"
                    break
        if group is None:
            group = _group_id(canonical)
        updated = document.model_copy(update={"independence_group": group, "url": canonical})
        assigned.append(updated)
        canonical_to_group[canonical] = group
        exact_to_group[content_hash] = group
        reasons[document.id] = reason
    return GroupingResult(documents=assigned, reasons=reasons)
