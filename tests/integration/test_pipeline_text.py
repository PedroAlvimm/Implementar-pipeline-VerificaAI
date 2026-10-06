from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.claims.schemas import (
    Claim,
    ClaimPriority,
    ClaimType,
    ClaimValidationResult,
    QuerySet,
)
from app.core.enums import AnalysisStatus, Verdict
from app.core.schemas import AnalysisCreate
from app.database.base import Base
from app.database.models import (
    ClaimRecord,
    DecisionRecord,
    EvidenceRecord,
    QueryRecord,
    ReportRecord,
    SearchResultRecord,
)
from app.database.repositories import AnalysisRepository
from app.database.session import build_engine, build_session_factory
from app.evidence.chunking import EvidenceDocument
from app.fact_checking.judgment import EvidenceDecision
from app.reports.builder import ReportBuilder
from app.risk_analysis.disabled import DisabledRiskAnalyzer
from app.search.contracts import SearchResult
from app.services.pipeline import AnalysisPipeline, PipelineLimits


class ScenarioServices:
    def __init__(self, scenario: dict[str, str]) -> None:
        self.scenario = scenario

    def extract(self, text: str) -> ClaimValidationResult:
        claim = Claim(
            id="claim_01",
            text=self.scenario["claim"],
            original_excerpt=text,
            claim_type=ClaimType.OTHER,
            checkable=True,
            priority=ClaimPriority.HIGH,
            entities=["Município Alfa"],
        )
        return ClaimValidationResult(accepted=[claim], rejected=[])

    def generate(self, claim: Claim) -> QuerySet:
        return QuerySet(claim_id=claim.id, queries=["consulta oficial", "consulta jornal"])

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        del limit
        count = 2 if self.scenario["verdict"] == "CONFLICTING" else 1
        return [
            SearchResult(
                title=f"Fonte {index}",
                url=f"https://fonte{index}.example/doc",
                snippet="resultado",
                domain=f"fonte{index}.example",
                published_at=datetime(2024, 1, 1, tzinfo=UTC),
                query=query,
                rank=index,
            )
            for index in range(1, count + 1)
        ]

    def load(self, result: SearchResult) -> EvidenceDocument:
        text = self.scenario["evidence"]
        if self.scenario["verdict"] == "CONFLICTING":
            text = (
                "O contrato confirma a compra de 10 ambulâncias."
                if "fonte1" in result.domain
                else "O relatório registra somente 8 ambulâncias."
            )
        return EvidenceDocument(
            id=f"doc_{result.domain}",
            text=text,
            title=result.title,
            url=result.url,
            domain=result.domain,
            published_at=result.published_at,
            independence_group=f"group_{result.domain}",
        )

    def judge(self, claim_id: str, claim_text: str, evidence) -> EvidenceDecision:
        del claim_text
        wanted = self.scenario["verdict"]
        label = Verdict.SUPPORTED if wanted == "CONFLICTING" else Verdict(wanted)
        if wanted == "CONFLICTING" and "8 ambulâncias" in evidence.text:
            label = Verdict.REFUTED
        quote = "" if label is Verdict.NEI else evidence.text
        return EvidenceDecision(
            claim_id=claim_id,
            evidence_id=evidence.evidence_id,
            label=label,
            reason="decisão baseada apenas no trecho",
            quoted_excerpt=quote,
            limitations=[],
        )


@pytest.fixture
def pipeline_factory(tmp_path: Path):
    engine = build_engine(f"sqlite:///{tmp_path / 'pipeline.sqlite3'}")
    Base.metadata.create_all(engine)
    sessions = build_session_factory(engine)
    repository = AnalysisRepository(sessions)

    def make(scenario: dict[str, str], **limit_overrides):
        services = ScenarioServices(scenario)
        limits = PipelineLimits(**limit_overrides)
        pipeline = AnalysisPipeline(
            repository=repository,
            sessions=sessions,
            claim_extractor=services,
            query_generator=services,
            search_provider=services,
            document_loader=services,
            judge=services,
            report_builder=ReportBuilder(),
            risk_analyzer=DisabledRiskAnalyzer(),
            limits=limits,
        )
        return pipeline, repository, sessions

    return make


@pytest.mark.parametrize(
    "fixture_name,expected",
    [
        ("supported.json", Verdict.SUPPORTED),
        ("refuted.json", Verdict.REFUTED),
        ("nei.json", Verdict.NEI),
        ("conflicting.json", Verdict.CONFLICTING),
    ],
)
def test_fake_pipeline_preserves_every_stage_and_four_verdicts(
    pipeline_factory, fixture_name: str, expected: Verdict
) -> None:
    scenario = json.loads((Path("tests/fixtures/demo") / fixture_name).read_text())
    pipeline, repository, sessions = pipeline_factory(scenario)
    created = repository.create(AnalysisCreate(input_type="text", content=scenario["text"]))

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.COMPLETED
    assert repository.get(created.id).clean_text == scenario["text"]
    with sessions() as session:
        for model in (
            ClaimRecord,
            QueryRecord,
            SearchResultRecord,
            EvidenceRecord,
            DecisionRecord,
            ReportRecord,
        ):
            assert session.scalar(select(func.count()).select_from(model)) >= 1
        report = session.scalar(select(ReportRecord)).payload
    assert report["claims"][0]["verdict"] == expected.value
    assert report["risk_status"]["status"] == "modelo_indisponivel"


def test_provider_disabled_is_explicit_failure(pipeline_factory) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, _ = pipeline_factory(scenario)
    pipeline.claim_extractor = None
    created = repository.create(AnalysisCreate(input_type="text", content=scenario["text"]))

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.FAILED
    assert result.error_code == "PROVIDER_DISABLED"


@pytest.mark.parametrize(
    "limits",
    [
        {"max_llm_calls": 0},
        {"max_llm_tokens": 1},
        {"max_artifact_bytes": 1},
    ],
)
def test_pipeline_budget_is_per_analysis_and_fails_closed(
    pipeline_factory, limits: dict[str, int]
) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, _ = pipeline_factory(scenario, **limits)
    created = repository.create(AnalysisCreate(input_type="text", content=scenario["text"]))

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.FAILED
    assert result.error_code == "RESOURCE_BUDGET_EXCEEDED"


def test_pipeline_enforces_five_minute_deadline(pipeline_factory) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, _ = pipeline_factory(scenario)
    moments = iter([0.0, 301.0])
    pipeline.clock = lambda: next(moments, 301.0)
    created = repository.create(AnalysisCreate(input_type="text", content=scenario["text"]))

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.FAILED
    assert result.error_code == "RESOURCE_BUDGET_EXCEEDED"


def test_completed_analysis_replay_does_not_overwrite_or_duplicate_cost(
    pipeline_factory,
) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, sessions = pipeline_factory(scenario)
    created = repository.create(AnalysisCreate(input_type="text", content=scenario["text"]))
    first = pipeline.run(created.id)

    replay = pipeline.run(created.id)

    assert replay.id == first.id
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(ReportRecord)) == 1


def test_partial_pipeline_has_explicit_limitations(pipeline_factory) -> None:
    scenario = json.loads(Path("tests/fixtures/demo/supported.json").read_text())
    pipeline, repository, _ = pipeline_factory(scenario)
    pipeline.document_loader.load = lambda result: (_ for _ in ()).throw(TimeoutError())
    created = repository.create(AnalysisCreate(input_type="text", content=scenario["text"]))

    result = pipeline.run(created.id)

    assert result.status == AnalysisStatus.COMPLETED_WITH_LIMITATIONS
    assert "claim_01:document_unavailable" in result.limitations
