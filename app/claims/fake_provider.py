from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class FakeLlmProvider:
    def __init__(self, responses: dict[str, dict]) -> None:
        self._responses = responses

    def generate_json(self, schema: type[SchemaT], messages: list[dict[str, str]]) -> SchemaT:
        del messages
        return schema.model_validate(self._responses[schema.__name__])
