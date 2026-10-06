from __future__ import annotations

import pytest

from app.core.enums import AnalysisStatus
from app.database.state_machine import InvalidStatusTransition, validate_transition


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (AnalysisStatus.PENDING, AnalysisStatus.COLLECTING),
        (AnalysisStatus.COLLECTING, AnalysisStatus.EXTRACTING_CLAIMS),
        (AnalysisStatus.EXTRACTING_CLAIMS, AnalysisStatus.SEARCHING),
        (AnalysisStatus.SEARCHING, AnalysisStatus.CHECKING),
        (AnalysisStatus.CHECKING, AnalysisStatus.COMPLETED),
        (AnalysisStatus.CHECKING, AnalysisStatus.COMPLETED_WITH_LIMITATIONS),
        (AnalysisStatus.SEARCHING, AnalysisStatus.FAILED),
    ],
)
def test_valid_analysis_transitions_are_accepted(
    current: AnalysisStatus, target: AnalysisStatus
) -> None:
    validate_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (AnalysisStatus.PENDING, AnalysisStatus.COMPLETED),
        (AnalysisStatus.COMPLETED, AnalysisStatus.CHECKING),
        (AnalysisStatus.FAILED, AnalysisStatus.PENDING),
        (AnalysisStatus.COLLECTING, AnalysisStatus.SEARCHING),
    ],
)
def test_invalid_analysis_transitions_are_rejected(
    current: AnalysisStatus, target: AnalysisStatus
) -> None:
    with pytest.raises(InvalidStatusTransition):
        validate_transition(current, target)
