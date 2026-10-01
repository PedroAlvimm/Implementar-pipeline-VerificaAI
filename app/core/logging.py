from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "content",
        "cookie",
        "cookies",
        "html",
        "original_html",
        "original_input",
        "text",
        "token",
    }
)


def redact_sensitive(value: Any) -> Any:
    """Return a log-safe copy of nested structured data."""

    if isinstance(value, Mapping):
        return {
            key: REDACTED if str(key).casefold() in SENSITIVE_KEYS else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value

