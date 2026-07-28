from __future__ import annotations

from pathlib import Path

from elmos_sql_transpiler.qualification import run_qualification


def test_separated_corpora_meet_local_syntax_goal_and_fail_closed() -> None:
    root = Path(__file__).resolve().parents[1] / "corpus"
    report = run_qualification(
        [
            root / "development/queries.json",
            root / "negative/queries.json",
            root / "holdout/queries.json",
            root / "representative/queries.json",
        ]
    )

    assert report["routeCount"] == 42
    assert report["syntax"] == {
        "eligible": 248,
        "ready": 248,
        "successRate": 1.0,
        "goal": 0.995,
        "goalMet": True,
    }
    assert report["negative"]["total"] == 44
    assert report["negative"]["blocked"] == 44
    assert report["negative"]["failClosedRate"] == 1.0
    assert report["routeCoverage"] == {
        "covered": 42,
        "required": 42,
        "minimumPositiveCasesPerRoute": 5,
        "requiredCorpusKinds": ["development", "holdout", "representative"],
        "gateMet": True,
        "failures": [],
    }
    assert report["failures"] == []
    assert report["localDecision"] == "READY_FOR_ENGINE_EXECUTION"
    assert report["sourceExecution"] == "NOT_RUN"
    assert report["targetExecution"] == "NOT_RUN"
    assert report["resultEquivalence"] == "NOT_RUN"
    assert report["certification"] == "NOT_CERTIFIED"
