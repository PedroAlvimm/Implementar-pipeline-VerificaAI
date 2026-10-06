from __future__ import annotations

from app.core.enums import AnalysisStatus


class InvalidStatusTransition(ValueError):
    pass


_ALLOWED: dict[AnalysisStatus, frozenset[AnalysisStatus]] = {
    AnalysisStatus.PENDING: frozenset({AnalysisStatus.COLLECTING, AnalysisStatus.FAILED}),
    AnalysisStatus.COLLECTING: frozenset({AnalysisStatus.EXTRACTING_CLAIMS, AnalysisStatus.FAILED}),
    AnalysisStatus.EXTRACTING_CLAIMS: frozenset({AnalysisStatus.SEARCHING, AnalysisStatus.FAILED}),
    AnalysisStatus.SEARCHING: frozenset({AnalysisStatus.CHECKING, AnalysisStatus.FAILED}),
    AnalysisStatus.CHECKING: frozenset(
        {
            AnalysisStatus.COMPLETED,
            AnalysisStatus.COMPLETED_WITH_LIMITATIONS,
            AnalysisStatus.FAILED,
        }
    ),
    AnalysisStatus.COMPLETED: frozenset(),
    AnalysisStatus.COMPLETED_WITH_LIMITATIONS: frozenset(),
    AnalysisStatus.FAILED: frozenset(),
}


def validate_transition(current: AnalysisStatus, target: AnalysisStatus) -> None:
    if target not in _ALLOWED[current]:
        raise InvalidStatusTransition(f"Transição inválida: {current} → {target}")
