from __future__ import annotations

import json
from pathlib import Path

from scripts.run_evaluation import evaluate_cases


def test_versioned_evaluation_corpus_covers_residual_risks() -> None:
    cases = json.loads(Path("tests/evaluation/cases.json").read_text(encoding="utf-8"))
    risks = {case["risk"] for case in cases}

    assert risks == {
        "negation",
        "conflicting_dates",
        "different_units",
        "copied_sources",
        "stale_sources",
        "partial_support",
        "quote_context",
        "prompt_injection",
        "technical_failure",
    }
    assert not any("probability" in key.casefold() for case in cases for key in case)


def test_all_fictional_evaluation_cases_match_expected_results() -> None:
    cases = json.loads(Path("tests/evaluation/cases.json").read_text(encoding="utf-8"))
    summary = evaluate_cases(cases)

    assert summary["failed"] == 0, summary["cases"]
    assert summary["passed"] == summary["total"] == 9
