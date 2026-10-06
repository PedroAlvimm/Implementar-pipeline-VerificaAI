from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.database.base import Base
from app.database.repositories import AnalysisRepository
from app.database.session import build_engine, build_session_factory
from app.ingestion.url_loader import build_safe_url_loader
from app.reports.builder import ReportBuilder
from app.risk_analysis.disabled import DisabledRiskAnalyzer
from app.services.demo import DemoServices
from app.services.jobs import JobExecutor
from app.services.pipeline import AnalysisPipeline, PipelineLimits


@dataclass(frozen=True)
class AppContainer:
    repository: AnalysisRepository
    sessions: Any
    executor: Any
    settings: Settings


def build_default_container(settings: Settings | None = None) -> AppContainer:
    current = settings or Settings()
    if current.database_url.startswith("sqlite:///"):
        database_path = Path(current.database_url.removeprefix("sqlite:///"))
        database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = build_engine(current.database_url)
    Base.metadata.create_all(engine)
    sessions = build_session_factory(engine)
    repository = AnalysisRepository(sessions)

    if current.provider_mode == "fake":
        demo = DemoServices()
        pipeline = AnalysisPipeline(
            repository=repository,
            sessions=sessions,
            claim_extractor=demo,
            query_generator=demo,
            search_provider=demo,
            document_loader=demo,
            judge=demo,
            report_builder=ReportBuilder(),
            risk_analyzer=DisabledRiskAnalyzer(),
            url_loader=build_safe_url_loader(current),
            limits=PipelineLimits(
                timeout_seconds=current.analysis_timeout_seconds,
                max_llm_calls=current.max_llm_calls,
                max_llm_tokens=current.max_llm_tokens,
                max_artifact_bytes=current.max_artifact_bytes_per_analysis,
                max_results_per_query=current.max_results_per_query,
            ),
        )
        runner = pipeline.run
    else:

        def runner(analysis_id: str) -> None:
            repository.fail(
                analysis_id,
                "PROVIDER_DISABLED",
                "Configure a montagem dos provedores externos antes de executar a análise.",
            )

    executor = JobExecutor(
        runner,
        max_workers=current.max_concurrent_analyses,
        max_queued=current.max_queued_jobs,
    )
    return AppContainer(repository, sessions, executor, current)
