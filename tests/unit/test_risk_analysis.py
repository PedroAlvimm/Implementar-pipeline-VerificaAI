from __future__ import annotations

import pytest

from app.risk_analysis.bertimbau import BertimbauRiskAnalyzer, RiskModelUnavailableError
from app.risk_analysis.disabled import DisabledRiskAnalyzer


def test_disabled_risk_analyzer_never_returns_a_label_or_score() -> None:
    result = DisabledRiskAnalyzer().analyze("Uma afirmação qualquer.")

    assert result == {
        "status": "modelo_indisponivel",
        "label": None,
        "score": None,
        "model_name": None,
        "model_version": None,
        "message": "O modelo de risco textual ainda não foi integrado.",
    }


def test_bertimbau_adapter_does_not_pretend_to_run_inference() -> None:
    with pytest.raises(
        RiskModelUnavailableError,
        match="BERTimbau ainda não foi integrado",
    ):
        BertimbauRiskAnalyzer().analyze("Uma afirmação qualquer.")
