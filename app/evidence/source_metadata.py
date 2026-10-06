from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.search.deduplication import DocumentCandidate


class SourceType(StrEnum):
    OFFICIAL = "OFFICIAL"
    SCIENTIFIC = "SCIENTIFIC"
    NEWS = "NEWS"
    INSTITUTIONAL = "INSTITUTIONAL"
    SOCIAL = "SOCIAL"
    UNKNOWN = "UNKNOWN"


class SourceMetadata(BaseModel):
    source_type: SourceType
    is_primary_source: bool
    has_author: bool
    has_publication_date: bool
    has_original_document: bool
    jurisdiction_match: bool | None
    temporal_match: bool | None
    independence_group: str | None


def describe_source(document: DocumentCandidate) -> SourceMetadata:
    domain = urlsplit(document.url).hostname or ""
    official = domain.endswith(".gov.br") or domain == "gov.br"
    scientific = domain.endswith(".edu") or "doi.org" in domain
    source_type = (
        SourceType.OFFICIAL
        if official
        else SourceType.SCIENTIFIC
        if scientific
        else SourceType.UNKNOWN
    )
    return SourceMetadata(
        source_type=source_type,
        is_primary_source=official,
        has_author=False,
        has_publication_date=False,
        has_original_document=official,
        jurisdiction_match=None,
        temporal_match=None,
        independence_group=document.independence_group,
    )
