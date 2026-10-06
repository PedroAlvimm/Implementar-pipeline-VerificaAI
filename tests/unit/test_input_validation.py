from __future__ import annotations

import pytest

from app.core.errors import InputValidationError
from app.ingestion.validation import validate_analysis_input


def test_text_input_is_trimmed_without_altering_internal_negation_or_numbers() -> None:
    result = validate_analysis_input("text", "  O município não comprou 10 doses.  ", 100)

    assert result.content == "O município não comprou 10 doses."
    assert result.input_type == "text"


@pytest.mark.parametrize("content", ["", "   "])
def test_empty_text_is_rejected(content: str) -> None:
    with pytest.raises(InputValidationError, match="vazia"):
        validate_analysis_input("text", content, 100)


def test_oversized_text_is_rejected() -> None:
    with pytest.raises(InputValidationError, match="limite"):
        validate_analysis_input("text", "a" * 101, 100)


@pytest.mark.parametrize("content", ["não é url", "https://", "ftp://example.org/file"])
def test_malformed_or_unsupported_url_is_rejected(content: str) -> None:
    with pytest.raises(InputValidationError):
        validate_analysis_input("url", content, 100)
