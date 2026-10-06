from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel

from app.core.errors import InputValidationError


class ValidatedInput(BaseModel):
    input_type: Literal["text", "url"]
    content: str


def validate_analysis_input(
    input_type: str, content: str, max_chars: int = 100_000
) -> ValidatedInput:
    if input_type not in {"text", "url"}:
        raise InputValidationError("Tipo de entrada inválido")
    normalized = content.strip()
    if not normalized:
        raise InputValidationError("A entrada não pode ser vazia")
    if len(normalized) > max_chars:
        raise InputValidationError("A entrada excede o limite permitido")
    if input_type == "url":
        parsed = urlsplit(normalized)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            raise InputValidationError("URL malformada ou protocolo não permitido")
    return ValidatedInput(input_type=input_type, content=normalized)
