from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class OriginalQuote:
    text: str
    start: int
    end: int


def map_quote_to_original(quote: str, evidence_text: str) -> OriginalQuote:
    normalized_quote = unicodedata.normalize("NFC", quote).strip()
    tokens = normalized_quote.split()
    if not tokens:
        raise ValueError("Citação vazia")
    normalized_evidence = unicodedata.normalize("NFC", evidence_text)
    pattern = re.compile(r"\s+".join(re.escape(token) for token in tokens))
    match = pattern.search(normalized_evidence)
    if match is None:
        raise ValueError("Citação não encontrada na evidência")
    text = match.group(0)
    if text not in evidence_text:
        raise ValueError("Não foi possível mapear a citação aos caracteres originais")
    start = evidence_text.index(text)
    return OriginalQuote(text=text, start=start, end=start + len(text))
