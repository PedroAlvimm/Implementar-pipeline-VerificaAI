from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_apply_safe_poc_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_host == "127.0.0.1"
    assert settings.max_input_chars == 100_000
    assert settings.max_download_bytes == 5 * 1024 * 1024
    assert settings.max_redirects == 5
    assert settings.external_timeout_seconds == 20
    assert settings.max_claims == 3
    assert settings.max_queries_per_claim == 4
    assert settings.max_results_per_query == 10
    assert settings.max_documents_per_claim == 5
    assert settings.max_evidence_per_claim == 5
    assert settings.max_concurrent_analyses == 2
    assert settings.max_queued_jobs == 10
    assert settings.analysis_timeout_seconds == 300
    assert settings.max_llm_calls == 20
    assert settings.max_llm_tokens == 100_000
    assert settings.max_artifact_bytes_per_analysis == 25 * 1024 * 1024
    assert settings.evidence_chunk_chars == 1_200
    assert settings.evidence_chunk_overlap_chars == 200
    assert settings.domain_requests_per_second == 1
    assert settings.domain_concurrency == 2
    assert settings.provider_attempts == 2


def test_fake_provider_is_rejected_outside_test_or_demo() -> None:
    with pytest.raises(ValidationError, match="fake"):
        Settings(app_env="production", provider_mode="fake", _env_file=None)


@pytest.mark.parametrize("app_env", ["test", "demo"])
def test_fake_provider_is_allowed_only_for_explicit_non_real_modes(app_env: str) -> None:
    settings = Settings(app_env=app_env, provider_mode="fake", _env_file=None)

    assert settings.provider_mode == "fake"


def test_real_provider_requires_both_llm_settings() -> None:
    with pytest.raises(ValidationError, match=r"OPENAI_API_KEY.*OPENAI_MODEL"):
        Settings(app_env="production", provider_mode="real", _env_file=None)
