from __future__ import annotations

from app.risk_analysis.base import RiskAnalysisResult


class RiskModelUnavailableError(RuntimeError):
    """Raised until the trained BERTimbau artifact is integrated."""


class BertimbauRiskAnalyzer:
    """Future adapter boundary; intentionally contains no inference code."""

    def analyze(self, text: str) -> RiskAnalysisResult:
        del text
        raise RiskModelUnavailableError("O BERTimbau ainda não foi integrado.")
