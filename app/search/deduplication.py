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
    canonical_urls = [canonicalize_url(document.url) for document in documents]
    parents = {url: url for url in canonical_urls}

    def root(url: str) -> str:
        parents.setdefault(url, url)
        while parents[url] != url:
            parents[url] = parents[parents[url]]
            url = parents[url]
        return url

    def join(left: str, right: str) -> None:
        left_root, right_root = root(left), root(right)
        parents[max(left_root, right_root)] = min(left_root, right_root)

    reasons: dict[str, str] = {}
    for index, document in enumerate(documents):
        canonical = canonical_urls[index]
        reason = "unique_source"
        if document.original_source:
            join(canonical, canonicalize_url(document.original_source))
            reason = "declared_original_source"
        for previous_index, previous in enumerate(documents[:index]):
            previous_url = canonical_urls[previous_index]
            match_reason = None
            if canonical == previous_url:
                match_reason = "canonical_url"
            elif document.text.strip() and document.text.split() == previous.text.split():
                match_reason = "exact_content_hash"
            elif _similarity(document.text, previous.text) >= 0.70:
                match_reason = "near_duplicate_content"
            if match_reason:
                join(canonical, previous_url)
                if reason == "unique_source":
                    reason = match_reason
        reasons[document.id] = reason
    assigned = [
        document.model_copy(
            update={
                "independence_group": _group_id(root(url)),
                "url": url,
            }
        )
        for document, url in zip(documents, canonical_urls, strict=True)
    ]
    return GroupingResult(documents=assigned, reasons=reasons)
