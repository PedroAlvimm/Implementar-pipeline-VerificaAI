from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalysisCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    input_type: Literal["text", "url"]
    content: str = Field(min_length=1)
