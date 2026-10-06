from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, environment-backed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["local", "test", "demo", "production"] = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    database_url: str = "sqlite:///./data/verificaai.sqlite3"
    artifacts_dir: Path = Path("data/artifacts")
    provider_mode: Literal["disabled", "fake", "real"] = "disabled"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    brave_search_api_key: SecretStr | None = None
    hf_token: SecretStr | None = None
    log_level: str = "INFO"
    risk_model_mode: Literal["disabled", "bertimbau"] = "disabled"
    bertimbau_cache_dir: Path = Path("data/models/bertimbau-v4")
    bertimbau_max_input_tokens: int = Field(default=512, ge=8, le=512)

    max_input_chars: int = 100_000
    max_download_bytes: int = 5 * 1024 * 1024
    max_redirects: int = 5
    external_timeout_seconds: int = 20
    max_claims: int = 3
    max_queries_per_claim: int = 4
    max_results_per_query: int = 10
    max_documents_per_claim: int = 5
    max_evidence_per_claim: int = 5
    max_concurrent_analyses: int = 2
    max_queued_jobs: int = 10
    analysis_timeout_seconds: int = 5 * 60
    max_llm_calls: int = 20
    max_llm_tokens: int = 100_000
    max_artifact_bytes_per_analysis: int = 25 * 1024 * 1024
    evidence_chunk_chars: int = 1_200
    evidence_chunk_overlap_chars: int = 200
    domain_requests_per_second: int = 1
    domain_concurrency: int = 2
    provider_attempts: int = 2

    @model_validator(mode="after")
    def validate_provider_mode(self) -> Settings:
        if self.provider_mode == "fake" and self.app_env not in {"test", "demo"}:
            raise ValueError("provider_mode=fake é permitido somente em test ou demo")
        if self.provider_mode == "real" and not (self.openai_api_key and self.openai_model):
            raise ValueError("OPENAI_API_KEY e OPENAI_MODEL são obrigatórios no modo real")
        return self
