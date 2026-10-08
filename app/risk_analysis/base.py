from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BERTResult(BaseModel):
    """Validated auxiliary output; the status spellings preserve legacy consumers."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    status: Literal["available", "modelo_indisponivel", "technical_error"]
    label: Literal["FALSA", "VERDADEIRA"] | None = None
    score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    model_name: str | None = Field(default=None, max_length=255)
    model_version: str | None = Field(default=None, max_length=255)
    message: str = Field(max_length=2000)

    @model_validator(mode="after")
    def validate_state(self) -> BERTResult:
        if self.status == "available":
            if self.label is None or self.score is None:
                raise ValueError("Available BERT requires label and score")
            if not (
                self.model_name
                and self.model_name.strip()
                and self.model_version
                and self.model_version.strip()
            ):
                raise ValueError("Available BERT requires model identity and version")
        elif self.label is not None or self.score is not None:
            raise ValueError("Unavailable or failed BERT cannot carry a prediction")
        return self

    def __getitem__(self, key: str):
        # ReportBuilder still consumes the old mapping interface during cutover.
        return self.model_dump()[key]


RiskAnalysisResult = BERTResult


class RiskAnalyzer(Protocol):
    def analyze(self, text: str) -> BERTResult:
        """Analyze textual risk without affecting factual verification."""
        ...
