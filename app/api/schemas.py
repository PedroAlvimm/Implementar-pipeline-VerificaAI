from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import AnalysisStatus


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=False, extra="forbid")

    input_type: Literal["text", "url"]
    content: str = Field(min_length=1)
    external_processing_consent: bool = False


class AnalysisAccepted(BaseModel):
    analysis_id: str
    status: AnalysisStatus


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    error_code: str | None
    error_message: str | None
    limitations: list[str]

