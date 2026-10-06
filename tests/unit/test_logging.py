from __future__ import annotations

from app.core.logging import redact_sensitive


def test_redaction_removes_sensitive_content_recursively() -> None:
    event = {
        "analysis_id": "analysis-123",
        "content": "texto privado",
        "nested": {
            "original_html": "<html>segredo</html>",
            "api_key": "sk-secret",
            "authorization": "Bearer token",
            "cookie": "session=secret",
        },
    }

    redacted = redact_sensitive(event)

    assert redacted == {
        "analysis_id": "analysis-123",
        "content": "[REDACTED]",
        "nested": {
            "original_html": "[REDACTED]",
            "api_key": "[REDACTED]",
            "authorization": "[REDACTED]",
            "cookie": "[REDACTED]",
        },
    }


def test_redaction_handles_sensitive_items_inside_lists() -> None:
    event = {"items": [{"text": "não registrar"}, {"status": "ok"}]}

    assert redact_sensitive(event) == {"items": [{"text": "[REDACTED]"}, {"status": "ok"}]}
