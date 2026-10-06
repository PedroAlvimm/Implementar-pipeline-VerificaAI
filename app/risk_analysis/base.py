from __future__ import annotations

from typing import Protocol, TypedDict


class RiskAnalysisResult(TypedDict):
    status: str
    label: str | None
    score: float | None
    model_name: str | None
    model_version: str | None
    message: str


class RiskAnalyzer(Protocol):
    def analyze(self, text: str) -> RiskAnalysisResult:
        """Analyze textual risk without affecting factual verification."""
        ...
