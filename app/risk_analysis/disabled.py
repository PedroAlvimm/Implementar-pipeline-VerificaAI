from __future__ import annotations

from app.risk_analysis.base import RiskAnalysisResult


class DisabledRiskAnalyzer:
    def analyze(self, text: str) -> RiskAnalysisResult:
        del text
        return {
            "status": "modelo_indisponivel",
            "label": None,
            "score": None,
            "model_name": None,
            "model_version": None,
            "message": "O modelo de risco textual ainda não foi integrado.",
        }
