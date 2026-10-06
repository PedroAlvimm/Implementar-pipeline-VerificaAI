from __future__ import annotations

import unicodedata
from datetime import UTC, datetime

import pytest

from app.core.enums import Verdict
from app.fact_checking.judgment import (
    EvidenceDecision,
    JudgmentEvidence,
    JudgmentValidationError,
    LlmEvidenceJudge,
    validate_decision,
)
from app.fact_checking.quotation import map_quote_to_original


def evidence(identifier: str = "ev_001", text: str = "O contrato prevê oito milhões de doses."):
    return JudgmentEvidence(
        evidence_id=identifier,
        text=text,
        source_title="Contrato",
        source_url="https://gov.example/contrato",
        source_domain="gov.example",
        published_at=datetime(2026, 1, 15, tzinfo=UTC),
        retrieved_at=datetime(2026, 10, 6, tzinfo=UTC),
        independence_group="grp_primary",
        is_primary_source=True,
        temporal_match=True,
    )


def decision(**changes) -> EvidenceDecision:
    values = {
        "claim_id": "claim_01",
        "evidence_id": "ev_001",
        "label": Verdict.REFUTED,
        "reason": "O documento registra oito milhões.",
        "quoted_excerpt": "O contrato prevê oito milhões de doses.",
        "limitations": [],
    }
    values.update(changes)
    return EvidenceDecision(**values)


def test_exact_quote_and_matching_ids_are_accepted() -> None:
    validated = validate_decision(decision(), "claim_01", evidence())

    assert validated.quoted_excerpt == "O contrato prevê oito milhões de doses."


@pytest.mark.parametrize(
    "invalid",
    [
        decision(evidence_id="ev_unknown"),
        decision(claim_id="claim_unknown"),
        decision(quoted_excerpt="Trecho de outra evidência."),
    ],
)
def test_unknown_ids_and_missing_quotes_are_rejected(invalid: EvidenceDecision) -> None:
    with pytest.raises(JudgmentValidationError):
        validate_decision(invalid, "claim_01", evidence())


def test_quote_mapping_returns_original_characters() -> None:
    original = "A ação pública não comprou 10 doses."
    decomposed_quote = unicodedata.normalize("NFD", "ação pública   não comprou 10 doses")

    mapped = map_quote_to_original(decomposed_quote, original)

    assert mapped.text == "ação pública não comprou 10 doses"
    assert mapped.text in original


def test_llm_judge_uses_required_evidence_only_prompt_and_one_repair() -> None:
    class Provider:
        def __init__(self) -> None:
            self.messages = []
            self.calls = 0

        def generate_json(self, schema, messages):
            self.messages = messages
            self.calls += 1
            return decision(quoted_excerpt="inventado") if self.calls == 1 else decision()

    provider = Provider()
    result = LlmEvidenceJudge(provider).judge(
        "claim_01", "O município comprou 10 milhões.", evidence()
    )

    assert result.label is Verdict.REFUTED
    assert provider.calls == 2
    system = provider.messages[0]["content"]
    assert "Use exclusivamente as evidências fornecidas" in system
    assert "Não utilize memória" in system
