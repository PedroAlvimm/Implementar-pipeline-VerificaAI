from __future__ import annotations

from app.database.repositories import AnalysisRepository


class RecoveryService:
    def __init__(self, repository: AnalysisRepository) -> None:
        self._repository = repository

    def fail_interrupted_analyses(self) -> int:
        return self._repository.fail_interrupted()
