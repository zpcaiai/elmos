"""The certification report: one machine-readable statement of what holds.

This is what a release gate consumes.  It deliberately reports *claims with
their evidence*, not a boolean, because "certified" with no visible basis is
the same failure mode the rest of the package exists to avoid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from elmos_repository_refactoring.catalog import PACKAGE_VERSION, SKILL_NAMES
from elmos_repository_refactoring.contracts import sha256_payload
from elmos_repository_refactoring.dispatcher import PENDING_SKILLS
from elmos_repository_refactoring.runtime import describe

from .cases import CASES
from .corpus import load

REPORT_PATH = Path(__file__).resolve().parents[1] / "golden" / "certification-report.json"


def build_report() -> dict[str, Any]:
    described = describe()
    corpus = [load(case) for case in CASES]
    recorded = [item for item in corpus if item is not None]
    return {
        "package": described["package"],
        "version": PACKAGE_VERSION,
        "catalog": {
            "total": len(SKILL_NAMES),
            "implemented": described["implementedCount"],
            "pending": sorted(PENDING_SKILLS),
        },
        "goldenCorpus": {
            "cases": len(CASES),
            "recorded": len(recorded),
            "skillsCovered": sorted({case.skill for case in CASES}),
            "statusMix": _counts(item["status"] for item in recorded),
            "corpusDigest": sha256_payload(
                {"cases": [item["inputDigest"] for item in sorted(recorded, key=_case_id)]}
            ),
        },
        "liveExecution": {
            "exercised": _live_toolchain_available(),
            "note": (
                "the live layer runs a real pytest and a real ruff through SubprocessExecutor "
                "over a materialized tree; when no toolchain is installed the live tests skip "
                "and the suite says so rather than reporting a pass"
            ),
        },
        "claims": [
            {
                "claim": "no third-party dependency is imported anywhere in the package",
                "evidence": "test_package_invariants.py::TestDependencyPurity",
            },
            {
                "claim": "only sandbox.py may spawn a process; there is no network-capable import",
                "evidence": "TestDependencyPurity::test_only_the_sandbox_may_spawn_a_process",
            },
            {
                "claim": "all 23 catalog Skills have a production handler and none is a stub",
                "evidence": "TestCatalogCoverage::test_no_handler_is_a_stub",
            },
            {
                "claim": "every Skill declares the payload fields it accepts and rejects the rest",
                "evidence": "TestFailClosedBehaviour::test_every_handler_declares_the_fields_it_accepts",
            },
            {
                "claim": "a payload cannot grant itself filesystem reach",
                "evidence": "TestFailClosedBehaviour::test_a_payload_cannot_grant_itself_filesystem_reach",
            },
            {
                "claim": "with no executor, blocking gates are undecided and the run does not pass",
                "evidence": (
                    "TestHonestyInvariants::"
                    "test_no_executor_means_no_gate_passes_on_evidence_it_does_not_have"
                ),
            },
            {
                "claim": "an undecodable source file lowers coverage; a binary asset does not",
                "evidence": "TestHonestyInvariants::test_an_unreadable_file_lowers_coverage_rather_than_vanishing",
            },
            {
                "claim": "a declared adapter level never exceeds the native engine level",
                "evidence": (
                    "TestHonestyInvariants::"
                    "test_a_signature_cannot_raise_a_language_above_what_the_code_can_do"
                ),
            },
            {
                "claim": "every corpus case is byte-identical across repeated dispatch",
                "evidence": "test_golden_corpus.py::test_case_is_deterministic",
            },
            {
                "claim": "every catalog Skill has at least one Golden-corpus case",
                "evidence": "test_certification_report.py::test_the_corpus_covers_every_catalog_skill",
            },
            {
                "claim": "every corpus case is byte-identical in a fresh process with a new hash seed",
                "evidence": (
                    "test_golden_corpus.py::test_every_case_is_deterministic_across_processes"
                ),
            },
            {
                "claim": "a pinned clock is threaded into every Skill that timestamps its output",
                "evidence": (
                    "TestHonestyInvariants::"
                    "test_a_pinned_clock_is_actually_threaded_into_timestamped_skills"
                ),
            },
            {
                "claim": (
                    "a snapshot materializes to disk without inventing content for a file it "
                    "cannot reproduce"
                ),
                "evidence": (
                    "test_live_toolchain.py::"
                    "test_an_unreproducible_file_is_reported_not_invented"
                ),
            },
            {
                "claim": (
                    "the pure core's cross-file rename survives a real pytest run over the "
                    "materialized tree"
                ),
                "evidence": (
                    "test_live_toolchain.py::test_the_transform_output_survives_a_real_test_run"
                ),
            },
            {
                "claim": "the sandbox refuses a non-allowlisted binary, an escaping cwd and leaks no host environment",
                "evidence": "test_live_toolchain.py::TestSandboxRefusals",
            },
            {
                "claim": "a timed-out command blocks the run and can never satisfy a gate",
                "evidence": "test_live_toolchain.py::test_a_timed_out_gate_blocks_the_run",
            },
            {
                "claim": "the suite is proven to fail on a real injected defect",
                "evidence": (
                    "test_suite_detects_regressions.py::"
                    "test_an_undecided_gate_reading_as_a_pass_is_observable"
                ),
            },
        ],
    }


def _live_toolchain_available() -> bool:
    import shutil

    return bool(shutil.which("pytest")) and bool(shutil.which("ruff"))


def _case_id(item: dict[str, Any]) -> str:
    return str(item["caseId"])


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items()))


def test_the_certification_report_is_current() -> None:
    """The report is committed, so a release can read it without running the suite."""

    import os

    report = build_report()
    if os.environ.get("ELMOS_UPDATE_GOLDEN") == "1" or not REPORT_PATH.exists():
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if os.environ.get("ELMOS_UPDATE_GOLDEN") != "1":
            import pytest

            pytest.fail("no committed certification report; re-record with ELMOS_UPDATE_GOLDEN=1")
        return
    committed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert committed == report, (
        "the committed certification report no longer matches what the package can claim; "
        "re-record with ELMOS_UPDATE_GOLDEN=1 after confirming the change is intended"
    )


def test_the_report_claims_nothing_that_is_not_tested() -> None:
    """Every claim must name a test that exists, or the report is decoration."""

    suite = Path(__file__).parent
    #: This module is excluded from its own search corpus.  Including it made
    #: every claim match the string that stated it, so the check passed while
    #: naming a test that had been renamed away — a self-satisfying assertion,
    #: which is worse than no assertion because it reads as coverage.
    body = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(suite.glob("test_*.py"))
        if path.name != Path(__file__).name
    )
    for entry in build_report()["claims"]:
        target = str(entry["evidence"]).rsplit("::", 1)[-1]
        assert target in body, f"claim '{entry['claim']}' names missing evidence '{target}'"


def test_the_report_agrees_with_the_catalog() -> None:
    report = build_report()
    assert report["catalog"]["pending"] == []
    assert report["catalog"]["implemented"] == report["catalog"]["total"] == len(SKILL_NAMES)
