from __future__ import annotations

import json

import httpx
import pytest

from app.claims.openai_provider import (
    LlmBudget,
    LlmOutputError,
    LlmProviderError,
    OpenAIResponsesProvider,
)
from app.claims.schemas import QuerySet
from app.core.privacy import PrivacyConsent


def response(text: str, tokens: int = 8) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "output": [{"content": [{"type": "output_text", "text": text}]}],
            "usage": {"total_tokens": tokens},
        },
    )


def provider(handler, *, key: str = "sk-never-log-this") -> OpenAIResponsesProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAIResponsesProvider(
        api_key=key,
        model="configured-model",
        consent=PrivacyConsent(granted=True),
        budget=LlmBudget(max_calls=3, max_tokens=100),
        client=client,
    )


def test_openai_adapter_requests_strict_json_schema_and_validates_result() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return response(
            '{"claim_id":"claim_01","queries":["uma consulta","site:gov.br documento"]}'
        )

    result = provider(handler).generate_json(
        QuerySet,
        [{"role": "user", "content": "<conteudo_nao_confiavel>texto</conteudo_nao_confiavel>"}],
    )

    assert result.claim_id == "claim_01"
    assert seen["model"] == "configured-model"
    assert seen["text"]["format"]["type"] == "json_schema"
    assert seen["text"]["format"]["strict"] is True


def test_invalid_json_gets_one_repair_attempt_then_succeeds() -> None:
    replies = iter([response("not-json"), response('{"claim_id":"claim_01","queries":["a","b"]}')])

    result = provider(lambda _request: next(replies)).generate_json(
        QuerySet, [{"role": "user", "content": "texto"}]
    )

    assert result.queries == ["a", "b"]


def test_second_invalid_response_is_rejected() -> None:
    with pytest.raises(LlmOutputError):
        provider(lambda _request: response("not-json")).generate_json(
            QuerySet, [{"role": "user", "content": "texto"}]
        )


@pytest.mark.parametrize(
    "failure",
    [httpx.TimeoutException("timeout"), httpx.Response(429, json={"error": "rate limit"})],
)
def test_provider_errors_are_explicit_and_never_leak_key(failure) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if isinstance(failure, Exception):
            raise failure
        failure.request = request
        return failure

    with pytest.raises(LlmProviderError) as caught:
        provider(handler).generate_json(QuerySet, [{"role": "user", "content": "texto"}])

    assert "sk-never-log-this" not in str(caught.value)
