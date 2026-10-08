from __future__ import annotations

from app.risk_analysis.base import RiskAnalysisResult


class DisabledRiskAnalyzer:
    def analyze(self, text: str) -> RiskAnalysisResult:
        del text
        return RiskAnalysisResult.model_validate(
            {
                "status": "modelo_indisponivel",
                "label": None,
                "score": None,
                "model_name": None,
                "model_version": None,
                "message": (
                    "Análise linguística auxiliar indisponível; não altera o resultado factual."
                ),
            }
        )
