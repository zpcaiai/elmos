"""Repository-scope pipeline: inventory -> discovery -> resumable batch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import elmos_polyglot_route.batch as batch_module
import elmos_polyglot_route.discovery as discovery_module
from elmos_polyglot_route.batch import CHECKPOINT_NAME, UnitStatus, run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository, propose_candidates
from elmos_polyglot_route.models import Language, RouteError
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


def test_python_inventory_includes_methods_and_never_silently_truncates_functions() -> None:
    mixed = (
        "def top(value: int) -> int:\n    return value\n\n"
        "class Hidden:\n    def method(self, value: int) -> int:\n        return value\n"
    )
    assert propose_candidates(mixed.encode(), "python") == ["top", "Hidden.method"]
    many = "\n".join(f"def function_{index}(value: int) -> int:\n    return value\n" for index in range(41))
    assert len(propose_candidates(many.encode(), "python")) == 41


@pytest.mark.parametrize(
    ("language", "source"),
    [
        ("go", "package pricing\nfunc calculate(value int64) int64 { return value }\n"),
        ("rust", "pub fn calculate(value: i64) -> i64 { value }\n"),
        ("cpp", "std::int64_t calculate(std::int64_t value) { return value; }\n"),
        ("objc", "long long calculate(long long value) { return value; }\n"),
        ("swift", "func calculate(_ value: Int64) -> Int64 { return value }\n"),
    ],
)
def test_all_native_project_sources_propose_function_obligations(
    language: Language,
    source: str,
) -> None:
    assert propose_candidates(source.encode(), language) == ["calculate"]


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
    unsupported = next(result for result in report["results"] if Path(result["source_path"]).name == "storage.py")
    assert any("UNSUPPORTED" in rejection["reason"] for rejection in unsupported["rejected_candidates"])


def test_discovery_refuses_a_plan_whose_content_changed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = _plan(repository)
    (repository / "src" / "pricing.py").write_text(MIGRATABLE + "\n# drift\n", encoding="utf-8")
    with pytest.raises(RouteError, match="WORK_UNIT_CONTENT_CHANGED"):
        discover_repository(plan, repository)


def test_repository_inventory_rejects_control_characters_in_source_paths(tmp_path: Path) -> None:
    repository = tmp_path / "control-character-repository"
    repository.mkdir()
    (repository / "unsafe\nname.py").write_text(MIGRATABLE, encoding="utf-8")

    with pytest.raises(RouteError, match="REPOSITORY_SOURCE_PATH_CONTROL_CHARACTER_FORBIDDEN"):
        plan_repository(repository, "local:customer-repository", "python", "typescript")


def test_repository_inventory_never_excludes_a_source_symlink_from_the_denominator(tmp_path: Path) -> None:
    repository = tmp_path / "source-symlink-repository"
    repository.mkdir()
    external = tmp_path / "external.py"
    external.write_text(MIGRATABLE, encoding="utf-8")
    (repository / "hidden.py").symlink_to(external)

    with pytest.raises(RouteError, match="REPOSITORY_SOURCE_SYMLINK_FORBIDDEN"):
        plan_repository(repository, "local:customer-repository", "python", "typescript")


def test_discovery_does_not_follow_a_path_replaced_by_an_intermediate_symlink(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    plan = _plan(repository)
    source_directory = repository / "src"
    real_directory = repository / "src-real"
    source_directory.rename(real_directory)
    source_directory.symlink_to(real_directory, target_is_directory=True)

    with pytest.raises(RouteError, match="WORK_UNIT_SOURCE_MISSING_OR_UNSAFE"):
        discover_repository(plan, repository)


def test_discovery_never_downgrades_missing_exact_toolchain_to_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)

    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:typescript")

    monkeypatch.setattr(discovery_module, "analyze", unavailable)
    with pytest.raises(RouteError, match="EXACT_TOOLCHAIN_UNAVAILABLE:typescript"):
        discover_repository(_plan(repository), repository)


@pytest.mark.parametrize(
    "failure",
    [
        "NATIVE_ANALYZER_FAILED:helper:panic",
        "NATIVE_ANALYZER_CONTRACT_INVALID:INVALID_FUNCTION_SIGNATURE",
    ],
)
def test_discovery_never_downgrades_a_native_analyzer_failure_to_unsupported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    repository = _repository(tmp_path)

    def crashed(*_args: object, **_kwargs: object) -> object:
        raise RouteError(failure)

    monkeypatch.setattr(discovery_module, "analyze", crashed)
    with pytest.raises(RouteError, match=failure.split(":", 1)[0]):
        discover_repository(_plan(repository), repository)


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


def test_discovery_rejects_more_than_ten_thousand_obligations_before_native_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "oversized-repository"
    repository.mkdir()
    (repository / "many.py").write_text(
        "\n".join(
            f"def function_{index}(value: int) -> int:\n    return value"
            for index in range(10_001)
        )
        + "\n",
        encoding="utf-8",
    )
    plan = plan_repository(repository, "local:oversized-repository", "python", "typescript")
    calls = 0

    def must_not_analyze(*_args: object, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        raise AssertionError("native analyzer must not run after the capacity preflight")

    monkeypatch.setattr(discovery_module, "analyze", must_not_analyze)
    with pytest.raises(RouteError, match="FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED"):
        discover_repository(plan, repository)
    assert calls == 0


def test_batch_runs_ready_units_and_never_rounds_up(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    ready = next(result for result in discovery["results"] if result["verdict"] == Verdict.READY)

    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{ready['id']}.json").write_text(
        json.dumps(
            [
                {"args": [100.0, 5.0], "expected": 105.0},
                {"args": [100.0, -1.0], "expected": 100.0},
            ]
        ),
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
    assert failed["reason_code"] == "SOURCE_VALIDATION_FAILED"
    assert failed["failure_stage"] == "SOURCE_BEHAVIOR_REPLAY"
    assert "target_path" not in failed


def test_batch_records_exact_toolchain_incident_without_aborting_the_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    ready = next(result for result in discovery["results"] if result["verdict"] == Verdict.READY)
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / f"{ready['id']}.json").write_text(
        json.dumps([{"args": [100.0, 5.0], "expected": 105.0}]),
        encoding="utf-8",
    )

    def unavailable(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise RouteError("EXACT_TOOLCHAIN_UNAVAILABLE:typescript")

    real_migrate = batch_module.migrate
    output = tmp_path / "batch"
    monkeypatch.setattr(batch_module, "migrate", unavailable)
    report = run_batch(discovery, repository, cases, output)
    failed = next(unit for unit in report["units"] if unit["id"] == ready["id"])
    assert failed["status"] == UnitStatus.FAILED
    assert failed["reason_code"] == "EXACT_TOOLCHAIN_UNAVAILABLE"
    assert failed["failure_stage"] == "ANALYSIS"
    assert "target_path" not in failed

    monkeypatch.setattr(batch_module, "migrate", real_migrate)
    rerun = run_batch(discovery, repository, cases, output)
    recovered = next(unit for unit in rerun["units"] if unit["id"] == ready["id"])
    assert recovered["status"] == UnitStatus.PASSED
    assert recovered.get("resumed_from_checkpoint") is not True
    assert rerun["resumed_count"] == len(discovery["results"]) - 1


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


def test_batch_does_not_resume_legacy_pass_without_source_validation_evidence(tmp_path: Path) -> None:
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
    passed = next(unit for unit in first["units"] if unit["status"] == UnitStatus.PASSED)
    assert passed["source_validation_status"] == "PASSED"
    assert passed["source_target_declared_case_equivalence"] == "PASSED"
    checkpoint = output / CHECKPOINT_NAME
    entries = [json.loads(line) for line in checkpoint.read_text(encoding="utf-8").splitlines()]
    for entry in entries:
        if entry["id"] == ready["id"]:
            entry.pop("source_validation_status", None)
            entry.pop("source_target_declared_case_equivalence", None)
    checkpoint.write_text("".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries), encoding="utf-8")

    rerun = run_batch(discovery, repository, cases, output)
    assert rerun["resumed_count"] == len(discovery["results"]) - 1
    refreshed = next(unit for unit in rerun["units"] if unit["id"] == ready["id"])
    assert refreshed.get("resumed_from_checkpoint") is not True
    assert refreshed["source_validation_status"] == "PASSED"


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
