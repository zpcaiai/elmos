"""Repository-scope pipeline: inventory -> discovery -> resumable batch."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route.batch import CHECKPOINT_NAME, UnitStatus, run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository, propose_candidates
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.repository import plan_repository

ROOT = Path(__file__).resolve().parents[1]

MIGRATABLE = """\
def calculate(subtotal: float, tax: float) -> float:
    if tax < 0:
        return subtotal
    return subtotal + tax
"""

UNTYPED = """\
def rounded(value):
    return value
"""

OUT_OF_PROFILE = """\
def persist(name: str) -> str:
    with open(name) as handle:
        return handle.read()
"""

NO_FUNCTION = """\
TAX_RATE = 0.2
"""


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "customer-repository"
    (repository / "src").mkdir(parents=True)
    (repository / "src" / "pricing.py").write_text(MIGRATABLE, encoding="utf-8")
    (repository / "src" / "rounding.py").write_text(UNTYPED, encoding="utf-8")
    (repository / "src" / "storage.py").write_text(OUT_OF_PROFILE, encoding="utf-8")
    (repository / "src" / "constants.py").write_text(NO_FUNCTION, encoding="utf-8")
    return repository


def _plan(repository: Path) -> dict[str, Any]:
    return plan_repository(repository, "local:customer-repository", "python", "typescript")


def test_proposed_candidates_never_decide_eligibility() -> None:
    assert propose_candidates(MIGRATABLE.encode(), "python") == ["calculate"]
    assert propose_candidates(NO_FUNCTION.encode(), "python") == []
    # A file that does not parse yields no proposal rather than a bad one.
    assert propose_candidates(b"def (:", "python") == []
    assert propose_candidates(b"\xff\xfe not utf-8", "python") == []


def test_discovery_classifies_every_unit_with_a_precise_verdict(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    report = discover_repository(_plan(repository), repository)

    assert report["kind"] == "elmos.repository-discovery-report"
    assert report["execution_status"] == "NOT_RUN"
    assert report["certification_status"] == "NOT_CERTIFIED"
    assert report["discovered_count"] == 4

    verdicts = {Path(result["source_path"]).name: result["verdict"] for result in report["results"]}
    assert verdicts["pricing.py"] == Verdict.READY
    assert verdicts["constants.py"] == Verdict.NO_CANDIDATE_DECLARATION
    assert verdicts["rounding.py"] == Verdict.UNSUPPORTED
    assert verdicts["storage.py"] == Verdict.UNSUPPORTED

    ready = next(result for result in report["results"] if result["verdict"] == Verdict.READY)
    assert ready["function_name"] == "calculate"
    assert ready["parameter_count"] == 2
    assert ready["required_inputs"] == ["behavior_cases_json"]

    # Rejections must name the construct that blocked the unit.
    unsupported = next(
        result for result in report["results"] if Path(result["source_path"]).name == "storage.py"
    )
    assert any("UNSUPPORTED" in rejection["reason"] for rejection in unsupported["rejected_candidates"])


def test_discovery_refuses_a_plan_whose_content_changed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = _plan(repository)
    (repository / "src" / "pricing.py").write_text(MIGRATABLE + "\n# drift\n", encoding="utf-8")
    with pytest.raises(RouteError, match="WORK_UNIT_CONTENT_CHANGED"):
        discover_repository(plan, repository)


def test_discovery_never_silently_selects_the_first_of_multiple_functions(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "multi-function-repository"
    repository.mkdir()
    (repository / "pricing.py").write_text(
        "def add(value: int, increment: int) -> int:\n"
        "    return value + increment\n\n"
        "def subtract(value: int, decrement: int) -> int:\n"
        "    return value - decrement\n",
        encoding="utf-8",
    )
    plan = plan_repository(
        repository,
        "local:multi-function-repository",
        "python",
        "typescript",
    )

    report = discover_repository(plan, repository)
    result = report["results"][0]

    assert result["verdict"] == Verdict.UNSUPPORTED
    assert result["reason"] == "MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION"
    assert [item["function_name"] for item in result["eligible_candidates"]] == [
        "add",
        "subtract",
    ]
    assert result["required_inputs"] == [
        "function_partition_manifest",
        "behavior_cases_json_per_function",
    ]


def test_discovery_refuses_a_plan_that_already_claims_execution(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = _plan(repository)
    plan["execution_status"] = "PASSED"
    with pytest.raises(RouteError, match="ALREADY_CLAIMS_EXECUTION"):
        discover_repository(plan, repository)


def test_batch_runs_ready_units_and_never_rounds_up(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    ready = next(result for result in discovery["results"] if result["verdict"] == Verdict.READY)

    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{ready['id']}.json").write_text(
        json.dumps([
            {"args": [100.0, 5.0], "expected": 105.0},
            {"args": [100.0, -1.0], "expected": 100.0},
        ]),
        encoding="utf-8",
    )

    report = run_batch(discovery, repository, cases, tmp_path / "batch")
    assert report["kind"] == "elmos.repository-batch-report"
    # One unit passed, three were not eligible: the batch is still PARTIAL.
    assert report["status"] == "PARTIAL"
    assert report["status_counts"][UnitStatus.PASSED] == 1
    assert report["status_counts"][UnitStatus.SKIPPED_NOT_READY] == 3
    assert report["unattempted_count"] == 3
    assert report["certification_status"] == "NOT_CERTIFIED"

    passed = next(unit for unit in report["units"] if unit["status"] == UnitStatus.PASSED)
    evidence = tmp_path / "batch" / passed["evidence_path"]
    assert evidence.is_file()
    assert json.loads(evidence.read_text())["status"] == "PASSED"


def test_batch_skips_ready_units_without_an_independent_corpus(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    cases = tmp_path / "cases"
    cases.mkdir()

    report = run_batch(discovery, repository, cases, tmp_path / "batch")
    assert report["status_counts"][UnitStatus.SKIPPED_NO_CASES] == 1
    assert report["attempted_count"] == 0


def test_batch_records_a_unit_failure_without_stopping_the_queue(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    ready = next(result for result in discovery["results"] if result["verdict"] == Verdict.READY)

    cases = tmp_path / "cases"
    cases.mkdir()
    # A corpus whose expectation is wrong must fail the unit, not the process.
    (cases / f"{ready['id']}.json").write_text(
        json.dumps([{"args": [100.0, 5.0], "expected": 999.0}]),
        encoding="utf-8",
    )

    report = run_batch(discovery, repository, cases, tmp_path / "batch")
    assert report["status"] == "PARTIAL"
    assert report["status_counts"][UnitStatus.FAILED] == 1
    failed = next(unit for unit in report["units"] if unit["status"] == UnitStatus.FAILED)
    assert failed["reason"]


def test_batch_resumes_from_its_checkpoint_without_redoing_work(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    ready = next(result for result in discovery["results"] if result["verdict"] == Verdict.READY)
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{ready['id']}.json").write_text(
        json.dumps([{"args": [100.0, 5.0], "expected": 105.0}]),
        encoding="utf-8",
    )
    output = tmp_path / "batch"

    first = run_batch(discovery, repository, cases, output)
    assert first["resumed_count"] == 0
    checkpoint = output / CHECKPOINT_NAME
    assert checkpoint.is_file()
    recorded = checkpoint.read_text(encoding="utf-8")

    second = run_batch(discovery, repository, cases, output)
    assert second["resumed_count"] == len(discovery["results"])
    assert second["status_counts"][UnitStatus.PASSED] == 1
    # Resuming must not append duplicate outcomes to the durable checkpoint.
    assert checkpoint.read_text(encoding="utf-8") == recorded


def test_batch_rejects_a_corrupt_checkpoint(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    output = tmp_path / "batch"
    output.mkdir(parents=True)
    (output / CHECKPOINT_NAME).write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(RouteError, match="BATCH_CHECKPOINT_CORRUPT"):
        run_batch(discovery, repository, tmp_path, output)


def test_batch_rejects_a_report_that_is_not_a_discovery_report(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(RouteError, match="DISCOVERY_REPORT_KIND_INVALID"):
        run_batch(_plan(repository), repository, tmp_path, tmp_path / "batch")
