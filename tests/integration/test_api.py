from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import dependencies
from app.api.dependencies import AppContainer, build_default_container
from app.core.config import Settings
from app.core.enums import AnalysisStatus
from app.database.base import Base
from app.database.models import ClaimRecord, ReportRecord
from app.database.repositories import AnalysisRepository
from app.database.session import build_engine, build_session_factory
from app.ingestion.url_loader import LoadedUrl
from app.main import create_app
from app.services.jobs import JobCapacityError, JobStatus


class StubExecutor:
    def __init__(self) -> None:
        self.ids: list[str] = []
        self.reject = False

    def submit(self, analysis_id: str) -> JobStatus:
        if self.reject:
            raise JobCapacityError("lotada")
        if analysis_id not in self.ids:
            self.ids.append(analysis_id)
        return JobStatus.QUEUED

    def status(self, analysis_id: str) -> JobStatus:
        return JobStatus.QUEUED


@pytest.fixture
def api(tmp_path: Path):
    engine = build_engine(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = build_session_factory(engine)
    repository = AnalysisRepository(sessions)
    executor = StubExecutor()
    settings = Settings(app_env="test", provider_mode="fake")
    app = create_app(AppContainer(repository, sessions, executor, settings))
    return TestClient(app), repository, sessions, executor


def test_post_returns_202_location_and_replays_idempotency_key(api) -> None:
    client, _, _, executor = api
    headers = {"Idempotency-Key": "request-1"}
    payload = {"input_type": "text", "content": "A prefeitura comprou dez ambulâncias."}

    first = client.post("/api/v1/analyses", json=payload, headers=headers)
    replay = client.post("/api/v1/analyses", json=payload, headers=headers)

    assert first.status_code == 202
    assert first.headers["location"].endswith(first.json()["analysis_id"])
    assert replay.json()["analysis_id"] == first.json()["analysis_id"]
    assert executor.ids == [first.json()["analysis_id"]]


@pytest.mark.parametrize(
    "payload",
    [
        {"input_type": "text", "content": "  "},
        {"input_type": "url", "content": "file:///etc/passwd"},
        {"input_type": "url", "content": "sem-esquema.example"},
    ],
)
def test_post_validates_text_and_url(api, payload: dict[str, str]) -> None:
    client, _, _, _ = api
    assert client.post("/api/v1/analyses", json=payload).status_code == 422


def test_idempotency_conflict_and_queue_capacity_have_explicit_codes(api) -> None:
    client, _, _, executor = api
    headers = {"Idempotency-Key": "same"}
    client.post(
        "/api/v1/analyses",
        json={"input_type": "text", "content": "Primeiro"},
        headers=headers,
    )

    conflict = client.post(
        "/api/v1/analyses",
        json={"input_type": "text", "content": "Outro"},
        headers=headers,
    )
    executor.reject = True
    capacity = client.post("/api/v1/analyses", json={"input_type": "text", "content": "Terceiro"})

    assert conflict.status_code == 409
    assert capacity.status_code == 429


def test_status_claims_and_report_endpoints_are_safe(api) -> None:
    client, repository, sessions, _ = api
    response = client.post(
        "/api/v1/analyses",
        json={"input_type": "text", "content": "Conteúdo <script>alert(1)</script>"},
    )
    analysis_id = response.json()["analysis_id"]
    repository.transition(analysis_id, AnalysisStatus.COLLECTING)
    repository.transition(analysis_id, AnalysisStatus.EXTRACTING_CLAIMS)
    repository.transition(analysis_id, AnalysisStatus.SEARCHING)
    repository.transition(analysis_id, AnalysisStatus.CHECKING)
    repository.complete_with_limitations(analysis_id, ["claim_02:search_unavailable"])
    with sessions.begin() as session:
        session.add(
            ClaimRecord(
                analysis_id=analysis_id,
                payload={"id": "claim_01", "text": "Afirmação auditável"},
            )
        )
        session.add(
            ReportRecord(
                analysis_id=analysis_id,
                payload={
                    "analysis_id": analysis_id,
                    "status": "COMPLETED_WITH_LIMITATIONS",
                    "claims": [],
                    "limitations": ["claim_02:search_unavailable"],
                },
            )
        )

    status = client.get(f"/api/v1/analyses/{analysis_id}")
    claims = client.get(f"/api/v1/analyses/{analysis_id}/claims")
    report = client.get(f"/api/v1/analyses/{analysis_id}/report")

    assert status.json()["status"] == "COMPLETED_WITH_LIMITATIONS"
    assert claims.json()[0]["id"] == "claim_01"
    assert report.json()["limitations"] == ["claim_02:search_unavailable"]
    assert "<script>" not in status.text + claims.text + report.text


def test_missing_analysis_is_404_and_local_cors_is_enabled(api) -> None:
    client, _, _, _ = api
    assert client.get("/api/v1/analyses/missing").status_code == 404
    response = client.options(
        "/api/v1/analyses",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:8501"


def test_real_provider_requires_explicit_external_processing_consent(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'consent.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = build_session_factory(engine)
    repository = AnalysisRepository(sessions)
    settings = Settings(
        app_env="test",
        provider_mode="real",
        openai_api_key="secret",
        openai_model="explicit-model",
    )
    client = TestClient(create_app(AppContainer(repository, sessions, StubExecutor(), settings)))

    response = client.post(
        "/api/v1/analyses", json={"input_type": "text", "content": "Texto factual"}
    )

    assert response.status_code == 403
    assert "consentimento" in response.json()["detail"].casefold()


@pytest.mark.parametrize(
    "content,expected",
    [
        ("Em 2024, o Município Alfa comprou 10 ambulâncias.", "SUPPORTED"),
        ("Em 2024, o Município Alfa comprou 20 ambulâncias.", "REFUTED"),
        ("O Município Alfa criará uma universidade em 2027.", "NEI"),
        ("Fontes divergem sobre 10 ambulâncias do Município Alfa.", "CONFLICTING"),
    ],
)
def test_default_demo_stack_runs_four_fictional_verdicts(
    tmp_path: Path, content: str, expected: str
) -> None:
    settings = Settings(
        app_env="demo",
        provider_mode="fake",
        database_url=f"sqlite:///{tmp_path / f'{expected}.sqlite3'}",
    )
    container = build_default_container(settings)
    client = TestClient(create_app(container))
    try:
        response = client.post("/api/v1/analyses", json={"input_type": "text", "content": content})
        analysis_id = response.json()["analysis_id"]
        container.executor.wait(analysis_id, timeout=2)
        with container.sessions() as session:
            report = session.scalar(
                select(ReportRecord).where(ReportRecord.analysis_id == analysis_id)
            )
        assert report.payload["claims"][0]["verdict"] == expected
        assert report.payload["risk_message"].endswith("BERTimbau.")
    finally:
        container.executor.shutdown()


def test_default_demo_stack_connects_safe_url_loader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        dependencies,
        "build_safe_url_loader",
        lambda settings: (
            lambda url: LoadedUrl(
                text="Em 2024, o Município Alfa comprou 10 ambulâncias.",
                title="Entrada coletada",
                canonical_url=url,
            )
        ),
    )
    settings = Settings(
        app_env="demo",
        provider_mode="fake",
        database_url=f"sqlite:///{tmp_path / 'url-demo.sqlite3'}",
    )
    container = dependencies.build_default_container(settings)
    client = TestClient(create_app(container))
    try:
        response = client.post(
            "/api/v1/analyses",
            json={"input_type": "url", "content": "https://public.example/noticia"},
        )
        analysis_id = response.json()["analysis_id"]
        container.executor.wait(analysis_id, timeout=2)

        status = client.get(f"/api/v1/analyses/{analysis_id}").json()
        report = client.get(f"/api/v1/analyses/{analysis_id}/report").json()

        assert status["status"] == "COMPLETED"
        assert report["title"] == "Entrada coletada"
    finally:
        container.executor.shutdown()
