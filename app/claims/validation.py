from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.claims.schemas import Claim, ClaimValidationResult, RejectedClaim


class UntrustedReferenceError(ValueError):
    pass


def validate_claims(
    source_text: str, candidates: list[Claim], limit: int = 3
) -> ClaimValidationResult:
    accepted: list[Claim] = []
    rejected: list[RejectedClaim] = []
    for candidate in candidates:
        if candidate.original_excerpt not in source_text:
            rejected.append(
                RejectedClaim(claim_id=candidate.id, reason="original_excerpt_not_found")
            )
        elif len(accepted) >= limit:
            rejected.append(RejectedClaim(claim_id=candidate.id, reason="claim_limit_exceeded"))
        else:
            accepted.append(candidate)
    return ClaimValidationResult(accepted=accepted, rejected=rejected)


def ensure_allowed_references(value: Any, *, allowed_ids: set[str], allowed_urls: set[str]) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized.endswith("_id") and isinstance(item, str) and item not in allowed_ids:
                raise UntrustedReferenceError(f"Identificador não permitido: {item}")
            if normalized.endswith("url") and isinstance(item, str) and item not in allowed_urls:
                raise UntrustedReferenceError(f"URL não permitida: {item}")
            ensure_allowed_references(item, allowed_ids=allowed_ids, allowed_urls=allowed_urls)
    elif isinstance(value, list):
        for item in value:
            ensure_allowed_references(item, allowed_ids=allowed_ids, allowed_urls=allowed_urls)
