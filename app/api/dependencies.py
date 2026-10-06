from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.database.base import Base
from app.database.repositories import AnalysisRepository
from app.database.session import build_engine, build_session_factory
from app.services.jobs import JobExecutor


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

    def unavailable_runner(analysis_id: str) -> None:
        repository.fail(
            analysis_id,
            "PROVIDER_DISABLED",
            "Configure os provedores externos antes de executar a análise.",
        )

    executor = JobExecutor(
        unavailable_runner,
        max_workers=current.max_concurrent_analyses,
        max_queued=current.max_queued_jobs,
    )
    return AppContainer(repository, sessions, executor, current)

