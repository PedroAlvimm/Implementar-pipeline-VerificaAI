from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.privacy import PrivacyConsent

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LlmProviderError(RuntimeError):
    pass


class LlmOutputError(LlmProviderError):
    pass


class LlmBudgetExceeded(LlmProviderError):
    pass


@dataclass
class LlmBudget:
    max_calls: int
    max_tokens: int
    calls: int = 0
    tokens: int = 0

    def reserve(self, estimated_tokens: int) -> None:
        if self.calls + 1 > self.max_calls or self.tokens + estimated_tokens > self.max_tokens:
            raise LlmBudgetExceeded("Orçamento da LLM excedido")
        self.calls += 1
        self.tokens += estimated_tokens

    def record_actual(self, actual_tokens: int, reserved_tokens: int) -> None:
        self.tokens += max(0, actual_tokens - reserved_tokens)
        if self.tokens > self.max_tokens:
            raise LlmBudgetExceeded("Orçamento da LLM excedido")


class OpenAIResponsesProvider:
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        consent: PrivacyConsent,
        budget: LlmBudget,
        client: httpx.Client | None = None,
        timeout: float = 20,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._consent = consent
        self._budget = budget
        self._client = client or httpx.Client(timeout=timeout, trust_env=False)

    def generate_json(self, schema: type[SchemaT], messages: list[dict[str, str]]) -> SchemaT:
        self._consent.require_external_processing()
        attempts = list(messages)
        last_error: Exception | None = None
        for attempt in range(2):
            estimate = max(1, sum(len(item.get("content", "")) for item in attempts) // 4)
            self._budget.reserve(estimate)
            payload = {
                "model": self._model,
                "input": attempts,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": schema.__name__,
                        "schema": schema.model_json_schema(),
                        "strict": True,
                    }
                },
            }
            try:
                response = self._client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                raise LlmProviderError("Timeout ao consultar o provedor de LLM") from exc
            if response.status_code == 429:
                raise LlmProviderError("Limite de uso do provedor de LLM atingido")
            if response.is_error:
                raise LlmProviderError(f"Falha do provedor de LLM: HTTP {response.status_code}")
            data = response.json()
            actual = int(data.get("usage", {}).get("total_tokens", estimate))
            self._budget.record_actual(actual, estimate)
            try:
                raw = data["output"][0]["content"][0]["text"]
                return schema.model_validate(json.loads(raw))
            except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                if attempt == 0:
                    attempts.append(
                        {
                            "role": "user",
                            "content": (
                                "A resposta anterior era inválida. Retorne somente JSON no schema."
                            ),
                        }
                    )
        raise LlmOutputError("O provedor retornou JSON inválido após uma correção") from last_error
