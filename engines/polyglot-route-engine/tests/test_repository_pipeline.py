"""Repository-scope pipeline: inventory -> discovery -> resumable batch."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import elmos_polyglot_route.batch as batch_module
import elmos_polyglot_route.discovery as discovery_module
from elmos_polyglot_route.batch import CHECKPOINT_NAME, UnitStatus, run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository, discover_unit, propose_candidates
from elmos_polyglot_route.models import (
    REPOSITORY_SURFACE_LANGUAGES,
    Language,
    RouteError,
    SemanticIR,
)
from elmos_polyglot_route.project_graph import build_project_graph
from elmos_polyglot_route.repository import plan_repository

ROOT = Path(__file__).resolve().parents[1]


def _as_analyze_many(single):
    """Adapt a per-function analyzer double onto the batched entry point.

    `discovery` binds `analyze_many` from `source_analyzer`; there has never
    been a `discovery.analyze`.  These doubles arrived from the other side of
    the merge written against the older single-name API.  Failures raised by
    the double still propagate, which is what the fail-closed assertions
    depend on.
    """

    def batched(source, language, function_names, **keywords):
        return {name: single(source, language, name, **keywords) for name in function_names}

    return batched


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


def test_python_inventory_surfaces_methods_and_never_silently_truncates_functions() -> None:
    """A method is a blocker, never a candidate and never a silent omission.

    This arrived from the other side of the merge asserting that a method is
    *proposed*.  `python_coverage_subjects` deliberately stopped doing that: a
    nested symbol carries an explicit blocking reason instead, so it cannot
    disappear from a file-level READY result.  The property the test protects
    is asserted here against the inventory that actually records it.
    """

    import ast

    from elmos_polyglot_route.discovery import MAX_CANDIDATES_PER_FILE, _candidate_inventory
    from elmos_polyglot_route.project_graph import python_coverage_subjects

    mixed = (
        "def top(value: int) -> int:\n    return value\n\n"
        "class Hidden:\n    def method(self, value: int) -> int:\n        return value\n"
    )
    assert propose_candidates(mixed.encode(), "python") == ["top"]

    by_qualified_name = {
        subject.qualified_name: subject
        for subject in python_coverage_subjects(ast.parse(mixed), "<candidate-source>")
    }
    assert "Hidden.method" in by_qualified_name
    assert by_qualified_name["Hidden.method"].candidate is False
    assert by_qualified_name["Hidden.method"].blocking_reasons

    # "Never silently truncates" lives on the inventory path.  `propose_candidates`
    # is bounded at MAX_CANDIDATES_PER_FILE by design and everything past that
    # bound becomes an explicit blocker; `_candidate_inventory` is the one that
    # must report every declaration and say so when it cannot.
    many = "\n".join(f"def function_{index}(value: int) -> int:\n    return value\n" for index in range(41))
    assert len(propose_candidates(many.encode(), "python")) == MAX_CANDIDATES_PER_FILE
    names, complete, reason = _candidate_inventory(many.encode(), "python")
    assert len(names) == 41
    assert complete is True
    assert reason is None

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
    assert verdicts["constants.py"] == Verdict.UNSUPPORTED
    assert verdicts["rounding.py"] == Verdict.UNSUPPORTED
    assert verdicts["storage.py"] == Verdict.UNSUPPORTED
    assert report["coverage_subject_count"] == 4
    assert report["coverage_blocker_count"] == 3

    ready = next(result for result in report["results"] if result["verdict"] == Verdict.READY)
    assert ready["function_name"] == "calculate"
    assert ready["parameter_count"] == 2
    assert ready["required_inputs"] == ["behavior_cases_json"]

    # Rejections must name the construct that blocked the unit.
    unsupported = next(result for result in report["results"] if Path(result["source_path"]).name == "storage.py")
    assert unsupported["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert "UNSUPPORTED" in unsupported["reason"]

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

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(unavailable))
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

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(crashed))
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
    results = report["results"]

    # The other side of this merge refused the whole file with
    # MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION.  Discovery now
    # partitions instead, which satisfies the same invariant more strongly:
    # both functions get their own work unit, so neither can be dropped and
    # the first can never stand in for the file.  See
    # test_discovery_partitions_multiple_functions_into_explicit_work_units.
    assert len(results) == 2
    assert [result["function_name"] for result in results] == ["add", "subtract"]
    assert all(result["parent_work_unit_id"] == "WU-00001" for result in results)
    assert report["work_unit_count"] == 2

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

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(must_not_analyze))
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
    assert json.loads(evidence.read_text())["status"] == "PASSED_LOCAL_UNCERTIFIED"

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
    # The other side of this merge carried `reason_code` / `failure_stage` on a
    # failed unit.  `batch.py` records the coded reason in `reason` instead; the
    # property under test -- an exact-toolchain incident fails one unit and
    # still produces a report -- is unchanged.
    assert failed["reason"].startswith("EXACT_TOOLCHAIN_UNAVAILABLE")
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
    # The other side of this merge resumed the PASSED unit too.  `batch.py`
    # treats the JSONL checkpoint as interruption state rather than an
    # authentication boundary: a caller who can edit it can also forge matching
    # target and evidence digests, so only non-success skips resume and every
    # PASSED unit is replayed.  See `_recorded_artifact_intact`.
    assert second["resumed_count"] == len(discovery["results"]) - 1
    assert second["status_counts"][UnitStatus.PASSED] == 1
    resumed_ids = {unit["id"] for unit in second["units"] if unit.get("resumed_from_checkpoint")}
    assert ready["id"] not in resumed_ids
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
    assert passed["execution_status"] is not None
    checkpoint = output / CHECKPOINT_NAME

    # This assertion arrived from the other side of the merge, where a PASS
    # carrying source-validation evidence *was* resumable and one missing that
    # evidence was not.  `batch.py` never resumes a PASS at all, which
    # subsumes the rule: strip the evidence or leave it, the unit is replayed
    # either way and its result is re-derived rather than trusted.
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
    assert refreshed["status"] == UnitStatus.PASSED

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

def test_inventory_accepts_the_content_addressed_web_repository_reference(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "module.py").write_text(
        "def value() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    repository_ref = (
        "repository-workspace:12345678-1234-1234-1234-123456789abc@0123456789abcdef0123456789abcdef01234567"
    )

    plan = plan_repository(repository, repository_ref, "python", "typescript")

    assert plan["repository_ref"] == repository_ref

@pytest.mark.parametrize(
    "repository_ref",
    [
        "repository-workspace:12345678-1234-1234-1234-123456789abc@main",
        "repository-workspace:12345678-1234-1234-1234-123456789abc@0123456789abcdef0123456789abcdef01234567/../escape",
        "repository-workspace:12345678-1234-1234-1234-123456789abc@0123456789abcdef0123456789abcdef012345678",
    ],
)
def test_inventory_rejects_unresolved_or_unsafe_web_repository_reference(
    tmp_path: Path,
    repository_ref: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "module.py").write_text(
        "def value() -> int:\n    return 1\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match="REPOSITORY_REF_INVALID"):
        plan_repository(repository, repository_ref, "python", "typescript")


def test_proposed_candidates_never_decide_eligibility() -> None:
    assert propose_candidates(MIGRATABLE.encode(), "python") == ["calculate"]
    assert propose_candidates(NO_FUNCTION.encode(), "python") == []
    # A file that does not parse yields no proposal rather than a bad one.
    assert propose_candidates(b"def (:", "python") == []
    assert propose_candidates(b"\xff\xfe not utf-8", "python") == []


_CANDIDATE_DISCOVERY_CASES: dict[Language, tuple[str, list[str]]] = {
    "java": ("public static long total(long value) { return value; }", ["total"]),
    "python": ("def total(value: int) -> int:\n    return value\n", ["total"]),
    "csharp": ("public static long Total(long value) { return value; }", ["Total"]),
    "typescript": ("export function total(value: number): number { return value; }", ["total"]),
    "javascript": ("export function total(value) { return value; }", ["total"]),
    "go": ("package sample\nfunc total(value int64) int64 { return value }", ["total"]),
    "rust": ("pub fn total(value: i64) -> i64 { value }", ["total"]),
    "cpp": ("std::int64_t total(std::int64_t value) { return value; }", ["total"]),
    "objc": ("long long total(long long value) { return value; }", ["total"]),
    "swift": ("public func total(_ value: Int) -> Int { return value }", ["total"]),
    "php": ("<?php\nfunction total(int $value): int { return $value; }", ["total"]),
    "kotlin": ("fun total(value: Long): Long = value", ["total"]),
    "react": ("export function total(value: number): number { return value; }", ["total"]),
    "flutter": ("int total(int value) => value;", ["total"]),
}


def test_candidate_discovery_fixtures_cover_the_repository_surface() -> None:
    assert set(_CANDIDATE_DISCOVERY_CASES) == set(REPOSITORY_SURFACE_LANGUAGES)


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        (language, source, expected)
        for language, (source, expected) in _CANDIDATE_DISCOVERY_CASES.items()
    ],
)
def test_candidate_discovery_covers_every_repository_language(
    language: Language,
    source: str,
    expected: list[str],
) -> None:
    assert propose_candidates(source.encode("utf-8"), language) == expected

def test_discovery_partitions_multiple_functions_into_explicit_work_units(
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
    results = report["results"]

    assert [result["id"] for result in results] == ["WU-00001-F001", "WU-00001-F002"]
    assert [result["function_name"] for result in results] == ["add", "subtract"]
    assert all(result["verdict"] == Verdict.READY for result in results)
    assert all(result["parent_work_unit_id"] == "WU-00001" for result in results)
    assert all(result["required_inputs"] == ["behavior_cases_json"] for result in results)
    assert report["planned_file_count"] == 1
    assert report["work_unit_count"] == 2

def test_discovery_preserves_an_eligible_function_but_blocks_a_rejected_peer(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "partial-symbol-repository"
    repository.mkdir()
    (repository / "mixed.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n\n"
        "def persist(name: str) -> str:\n"
        "    with open(name) as handle:\n"
        "        return handle.read()\n",
        encoding="utf-8",
    )
    plan = plan_repository(
        repository,
        "local:partial-symbol-repository",
        "python",
        "typescript",
    )

    report = discover_repository(plan, repository)

    assert [result["id"] for result in report["results"]] == ["WU-00001", "WU-00001-F002"]
    ready, blocker = report["results"]
    assert ready["verdict"] == Verdict.READY
    assert ready["function_name"] == "add"
    assert blocker["verdict"] == Verdict.UNSUPPORTED
    assert blocker["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert ready["coverage_key"] != blocker["coverage_key"]
    assert report["ready_count"] == 1
    assert report["coverage_subject_count"] == 2
    assert report["coverage_blocker_count"] == 1

    cases = tmp_path / "partial-cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text(
        json.dumps([{"args": [2, 3], "expected": 5}]),
        encoding="utf-8",
    )
    batch = run_batch(report, repository, cases, tmp_path / "partial-batch")
    assert batch["status"] == "PARTIAL"
    assert batch["status_counts"] == {
        UnitStatus.PASSED: 1,
        UnitStatus.SKIPPED_NOT_READY: 1,
    }

def test_native_module_inventory_preserves_a_rejected_peer_as_a_graph_blocker(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "typescript-partial-symbol-repository"
    repository.mkdir()
    (repository / "mixed.ts").write_text(
        "export function add(left: number, right: number): number {\n"
        "  return left + right;\n"
        "}\n\n"
        "export function persist(value: number): number {\n"
        "  const saved = value;\n"
        "  return saved;\n"
        "}\n",
        encoding="utf-8",
    )
    repository_ref = "local:typescript-partial-symbol-repository"
    report = discover_repository(
        plan_repository(repository, repository_ref, "typescript", "python"),
        repository,
    )

    assert report["module_inventory_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 1,
    }
    assert report["coverage_subject_count"] == 2
    assert report["coverage_blocker_count"] == 1
    assert report["ready_count"] == 1
    ready, blocker = report["results"]
    assert ready["verdict"] == Verdict.READY
    assert ready["function_name"] == "add"
    assert blocker["verdict"] == Verdict.UNSUPPORTED
    assert blocker["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert ready["coverage_key"] != blocker["coverage_key"]

    graph = build_project_graph(repository, repository_ref, report)
    assert graph["repository_complete"] is False
    native_subjects = [
        node
        for node in graph["nodes"]
        if node["language"] == "typescript" and node["kind"] == "symbol"
    ]
    assert len(native_subjects) == 2
    assert len({node["attributes"]["coverage_key"] for node in native_subjects}) == 2
    obligations = graph["diagnostic_obligations"]
    assert any(
        obligation["code"] == "NATIVE_SYMBOL_SEMANTIC_ANALYSIS_NOT_PASSED"
        and obligation["node_id"]
        == next(node["id"] for node in native_subjects if node["name"] == "persist")
        for obligation in obligations
    )

def test_inventory_integrity_failure_is_not_misreported_as_unsupported_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "typescript-inventory-failure"
    repository.mkdir()
    (repository / "sample.ts").write_text(
        "export function total(value: number): number { return value; }\n",
        encoding="utf-8",
    )

    def fail_inventory(_source: Path, _language: Language) -> dict[str, Any]:
        raise RouteError("TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE")

    monkeypatch.setattr(discovery_module, "inventory_module", fail_inventory)
    report = discover_repository(
        plan_repository(
            repository,
            "local:typescript-inventory-failure",
            "typescript",
            "python",
        ),
        repository,
    )

    assert report["verdict_counts"] == {Verdict.NOT_RUN: 1}
    assert report["ready_count"] == 0
    assert report["module_inventory_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 1,
        "PASSED": 0,
    }
    [blocked] = report["results"]
    assert blocked["verdict"] == Verdict.NOT_RUN
    assert blocked["blocker_code"] == "COMPILER_MODULE_ENUMERATION_NOT_PASSED"
    assert blocked["required_inputs"] == ["restore_analyzer_execution_and_replay"]
    assert blocked["source_symbol"]["semantic_status"] == "NOT_RUN"
    assert "TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE" in blocked["reason"]

def test_completed_source_diagnostics_from_inventory_remain_semantic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "cpp-source-diagnostics"
    repository.mkdir()
    (repository / "sample.cpp").write_text(
        "long long total(long long value) { return value + ; }\n",
        encoding="utf-8",
    )

    def reject_source(_source: Path, _language: Language) -> dict[str, Any]:
        raise RouteError("SOURCE_DIAGNOSTICS_BLOCK_ANALYSIS:expected expression")

    monkeypatch.setattr(discovery_module, "inventory_module", reject_source)
    report = discover_repository(
        plan_repository(
            repository,
            "local:cpp-source-diagnostics",
            "cpp",
            "python",
        ),
        repository,
    )

    assert report["verdict_counts"] == {Verdict.UNSUPPORTED: 1}
    assert report["module_inventory_status_counts"] == {
        "FAILED": 1,
        "NOT_RUN": 0,
        "PASSED": 0,
    }
    [blocked] = report["results"]
    assert blocked["verdict"] == Verdict.UNSUPPORTED
    assert blocked["blocker_code"] == "COMPILER_MODULE_ENUMERATION_REJECTED_SOURCE"
    assert blocked["required_inputs"] == ["explicit_symbol_conversion_support"]
    assert blocked["source_symbol"]["semantic_status"] == "BLOCKED"

@pytest.mark.parametrize(
    ("language", "diagnostic", "expected"),
    [
        ("python", "PYTHON_ANNOTATED_DECLARATION_WITHOUT_VALUE", Verdict.UNSUPPORTED),
        ("python", "PYTHON_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET", Verdict.UNSUPPORTED),
        ("python", "PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET", Verdict.UNSUPPORTED),
        ("python", "PYTHON_UNSUPPORTED_LOCAL_TYPE:list", Verdict.UNSUPPORTED),
        ("python", "CONDITION_MUST_BE_BOOLEAN", Verdict.UNSUPPORTED),
        ("python", "DUPLICATE_PARAMETER:value", Verdict.UNSUPPORTED),
        ("python", "LET_NAME_ALREADY_BOUND:price", Verdict.UNSUPPORTED),
        ("python", "LET_TYPE_MISMATCH:integer:number", Verdict.UNSUPPORTED),
        ("python", "OPERAND_TYPE_MISMATCH:+:integer:boolean", Verdict.UNSUPPORTED),
        ("python", "RETURN_TYPE_MISMATCH:integer:string", Verdict.UNSUPPORTED),
        ("python", "STRING_ORDERING_OUTSIDE_CERTIFIED_SUBSET:<", Verdict.UNSUPPORTED),
        ("python", "UNDECLARED_NAME:bonus", Verdict.UNSUPPORTED),
        ("python", "FUNCTION_NOT_FOUND:total", Verdict.NOT_RUN),
        ("python", "INVALID_LET_STATEMENT", Verdict.NOT_RUN),
        ("go", "GO_INVALID_LITERAL", Verdict.UNSUPPORTED),
        ("go", "GO_ONE_NAME_PER_PARAMETER_REQUIRED", Verdict.UNSUPPORTED),
        ("rust", "RUST_INVALID_FLOAT", Verdict.UNSUPPORTED),
        ("rust", "RUST_PARAMETER_IDENTIFIER_REQUIRED", Verdict.UNSUPPORTED),
        ("typescript", "TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED", Verdict.UNSUPPORTED),
        (
            "typescript",
            "NATIVE_ANALYZER_FAILED:/opt/elmos/node:TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED",
            Verdict.UNSUPPORTED,
        ),
        (
            "typescript",
            "TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE:UNSUPPORTED_EXPRESSION:forged",
            Verdict.NOT_RUN,
        ),
        (
            "typescript",
            "NATIVE_ANALYZER_FAILED:/opt/elmos/node:"
            "TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE:UNSUPPORTED_EXPRESSION:forged",
            Verdict.NOT_RUN,
        ),
        (
            "rust",
            "NATIVE_ANALYZER_FAILED:/opt/elmos/cargo:process\nRUST_INVALID_INTEGER",
            Verdict.NOT_RUN,
        ),
        ("javascript", "JAVASCRIPT_ANALYZER_SNAPSHOT_UNSAFE", Verdict.NOT_RUN),
    ],
)
def test_analyzer_failure_classifier_uses_primary_language_owned_code(
    language: Language,
    diagnostic: str,
    expected: str,
) -> None:
    assert discovery_module._analyzer_failure_verdict(RouteError(diagnostic), language) == expected

def test_real_typescript_domain_rejection_is_semantic_not_environmental(tmp_path: Path) -> None:
    repository = tmp_path / "typescript-domain-rejection"
    repository.mkdir()
    (repository / "sample.ts").write_text(
        "export function negate(value: number): number { return -value; }\n",
        encoding="utf-8",
    )

    report = discover_repository(
        plan_repository(
            repository,
            "local:typescript-domain-rejection",
            "typescript",
            "python",
        ),
        repository,
    )

    assert report["module_inventory_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 1,
    }
    assert report["verdict_counts"] == {Verdict.UNSUPPORTED: 1}
    [blocked] = report["results"]
    assert blocked["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert blocked["source_symbol"]["semantic_status"] == "FAILED"
    assert "TYPESCRIPT_UNARY_MINUS_LITERAL_REQUIRED" in blocked["reason"]

def test_completed_but_failed_module_enumeration_remains_an_explicit_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "cpp-enumeration-failure"
    repository.mkdir()
    (repository / "sample.cpp").write_text(
        "long long total(long long value) { return value; }\n",
        encoding="utf-8",
    )

    def failed_inventory(source: Path, language: Language) -> dict[str, Any]:
        return {
            "enumeration_status": "FAILED",
            "analyzer": "test-analyzer",
            "analyzer_version": "1",
            "subjects": [],
            "diagnostics": [f"MAIN_FILE_DECLARATION_SPAN_INVALID:{language}:{source.name}"],
        }

    monkeypatch.setattr(discovery_module, "inventory_module", failed_inventory)
    report = discover_repository(
        plan_repository(
            repository,
            "local:cpp-enumeration-failure",
            "cpp",
            "python",
        ),
        repository,
    )

    assert report["verdict_counts"] == {Verdict.UNSUPPORTED: 1}
    [blocked] = report["results"]
    assert blocked["verdict"] == Verdict.UNSUPPORTED
    assert blocked["source_symbol"]["semantic_status"] == "BLOCKED"
    assert blocked["required_inputs"] == ["explicit_symbol_conversion_support"]


@pytest.mark.parametrize(
    ("enumeration_status", "diagnostics", "include_diagnostics"),
    [
        ("FAILED", None, True),
        ("FAILED", {}, True),
        ("FAILED", ["valid-diagnostic", 7], True),
        ("FAILED", [], False),
        ("PASSED", None, True),
    ],
    ids=[
        "failed-not-a-list",
        "failed-mapping",
        "failed-non-string-item",
        "failed-missing-key",
        "passed-not-a-list",
    ],
)
def test_discovery_rejects_invalid_module_inventory_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    enumeration_status: str,
    diagnostics: object,
    include_diagnostics: bool,
) -> None:
    repository = tmp_path / "invalid-module-inventory-diagnostics"
    repository.mkdir()
    (repository / "sample.cpp").write_text(
        "long long total(long long value) { return value; }\n",
        encoding="utf-8",
    )

    def invalid_inventory(_source: Path, _language: Language) -> dict[str, Any]:
        inventory: dict[str, Any] = {
            "enumeration_status": enumeration_status,
            "analyzer": "test-analyzer",
            "analyzer_version": "1",
            "subjects": [],
        }
        if include_diagnostics:
            inventory["diagnostics"] = diagnostics
        return inventory

    monkeypatch.setattr(discovery_module, "inventory_module", invalid_inventory)
    with pytest.raises(
        RouteError,
        match=r"^MODULE_INVENTORY_DIAGNOSTICS_INVALID:sample\.cpp$",
    ):
        discover_repository(
            plan_repository(
                repository,
                "local:invalid-module-inventory-diagnostics",
                "cpp",
                "python",
            ),
            repository,
        )


def test_discovery_blocks_duplicate_python_names_instead_of_reusing_the_first_ast_node(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "duplicate-symbol-repository"
    repository.mkdir()
    (repository / "duplicate.py").write_text(
        "def value() -> int:\n    return 1\n\ndef value() -> int:\n    return 2\n",
        encoding="utf-8",
    )

    report = discover_repository(
        plan_repository(repository, "local:duplicate-symbols", "python", "typescript"),
        repository,
    )

    assert report["ready_count"] == 0
    assert report["coverage_subject_count"] == 2
    assert report["coverage_blocker_count"] == 2
    assert {result["blocker_code"] for result in report["results"]} == {"PYTHON_DUPLICATE_TOP_LEVEL_FUNCTION_NAME"}
    assert len({result["coverage_key"] for result in report["results"]}) == 2

def test_discovery_blocks_every_python_candidate_beyond_the_bounded_limit(tmp_path: Path) -> None:
    repository = tmp_path / "candidate-limit-repository"
    repository.mkdir()
    (repository / "many.py").write_text(
        "\n".join(f"def value_{index}() -> int:\n    return {index}\n" for index in range(41)),
        encoding="utf-8",
    )

    report = discover_repository(
        plan_repository(repository, "local:candidate-limit", "python", "typescript"),
        repository,
    )

    assert report["ready_count"] == 40
    assert report["coverage_subject_count"] == 41
    assert report["coverage_blocker_count"] == 1
    blocker = next(result for result in report["results"] if result["verdict"] != Verdict.READY)
    assert blocker["id"] == "WU-00001-F041"
    assert blocker["blocker_code"] == "PYTHON_CANDIDATE_LIMIT_EXCEEDED"

def test_non_python_candidate_rejection_remains_an_explicit_batch_blocker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "java-partial-repository"
    repository.mkdir()
    (repository / "Sample.java").write_text(
        "public final class Sample {\n"
        "  public static long good(long value) { return value; }\n"
        "  public static long rejected(long value) { return value; }\n"
        "}\n",
        encoding="utf-8",
    )

    def fake_analyze(source: Path, language: Language, function_name: str) -> SemanticIR:
        if function_name == "rejected":
            raise RouteError("UNSUPPORTED_STATEMENT:side_effect")
        return SemanticIR.from_mapping(
            {
                "schema_version": "1.0.0",
                "source_language": language,
                "source_file": source.name,
                "analyzer": "adversarial-test",
                "analyzer_version": "1",
                "functions": [
                    {
                        "name": function_name,
                        "parameters": [{"name": "value", "type": "integer"}],
                        "return_type": "integer",
                        "body": [
                            {
                                "kind": "return",
                                "expression": {"kind": "name", "value": "value"},
                            }
                        ],
                    }
                ],
                "diagnostics": [],
            }
        )

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(fake_analyze))
    plan = plan_repository(repository, "local:java-partial", "java", "typescript")
    report = discover_repository(plan, repository)

    assert [result["id"] for result in report["results"]] == ["WU-00001", "WU-00001-F002"]
    ready, blocker = report["results"]
    assert ready["verdict"] == Verdict.READY
    assert ready["function_name"] == "good"
    assert blocker["verdict"] == Verdict.UNSUPPORTED
    assert blocker["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert report["candidate_obligation_count"] == 1

    cases = tmp_path / "empty-cases"
    cases.mkdir()
    batch = run_batch(report, repository, cases, tmp_path / "java-partial-batch")
    assert batch["status"] == "PARTIAL"
    assert batch["status_counts"] == {
        UnitStatus.SKIPPED_NOT_READY: 1,
        UnitStatus.SKIPPED_NO_CASES: 1,
    }

def test_per_symbol_integrity_failure_invalidates_earlier_ready_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "typescript-per-symbol-integrity"
    repository.mkdir()
    (repository / "sample.ts").write_text(
        "export function first(value: number): number { return value; }\n\n"
        "export function second(value: number): number { return value; }\n",
        encoding="utf-8",
    )

    def fail_second(source: Path, language: Language, function_name: str) -> SemanticIR:
        if function_name == "second":
            raise RouteError("TYPESCRIPT_ANALYZER_SNAPSHOT_UNSAFE")
        return SemanticIR.from_mapping(
            {
                "schema_version": "1.0.0",
                "source_language": language,
                "source_file": source.name,
                "analyzer": "adversarial-test",
                "analyzer_version": "1",
                "functions": [
                    {
                        "name": function_name,
                        "parameters": [{"name": "value", "type": "number"}],
                        "return_type": "number",
                        "body": [
                            {
                                "kind": "return",
                                "expression": {"kind": "name", "value": "value"},
                            }
                        ],
                    }
                ],
                "diagnostics": [],
            }
        )

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(fail_second))
    report = discover_repository(
        plan_repository(
            repository,
            "local:typescript-per-symbol-integrity",
            "typescript",
            "python",
        ),
        repository,
    )

    assert report["ready_count"] == 0
    assert report["verdict_counts"] == {Verdict.NOT_RUN: 2}
    assert report["module_inventory_status_counts"] == {
        "FAILED": 0,
        "NOT_RUN": 0,
        "PASSED": 1,
    }
    assert {result["blocker_code"] for result in report["results"]} == {
        "NATIVE_ANALYZER_EXECUTION_NOT_PASSED"
    }
    assert all(result["verdict"] == Verdict.NOT_RUN for result in report["results"])
    assert all(
        result["source_symbol"]["semantic_status"] == "NOT_RUN"
        for result in report["results"]
    )
    assert all(
        result["required_inputs"] == ["restore_analyzer_execution_and_replay"]
        for result in report["results"]
    )

def test_discovery_rejects_intermediate_symlink_escape_without_touching_sentinel(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    sibling = tmp_path / "repo-secret"
    sibling.mkdir()
    sentinel = sibling / "secret.py"
    sentinel.write_text("SECRET = 'retain me'\n", encoding="utf-8")
    (repository / "escape").symlink_to(sibling, target_is_directory=True)

    with pytest.raises(RouteError, match="WORK_UNIT_PATH_SYMLINK_REJECTED"):
        discover_unit(
            repository,
            {"id": "WU-00001", "source_path": "escape/secret.py"},
            "python",
        )

    assert sentinel.read_text(encoding="utf-8") == "SECRET = 'retain me'\n"

def test_batch_resumes_only_non_success_checkpoint_outcomes(tmp_path: Path) -> None:
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
    assert second["resumed_count"] == len(discovery["results"]) - 1
    assert second["status_counts"][UnitStatus.PASSED] == 1
    # A successful unit is replayed because the mutable checkpoint is not a
    # trust anchor; the three explicit non-ready outcomes may be resumed.
    assert checkpoint.read_text(encoding="utf-8") != recorded

def test_batch_reexecutes_a_forged_pass_checkpoint_and_restores_evidence(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "forged-checkpoint-repository"
    repository.mkdir()
    (repository / "value.py").write_text(
        "def value(number: int) -> int:\n    return number + 1\n",
        encoding="utf-8",
    )
    discovery = discover_repository(
        plan_repository(repository, "local:forged-checkpoint", "python", "typescript"),
        repository,
    )
    ready = discovery["results"][0]
    cases = tmp_path / "forged-checkpoint-cases"
    cases.mkdir()
    (cases / f"{ready['id']}.json").write_text(
        '[{"args": [1], "expected": 2}]\n',
        encoding="utf-8",
    )
    output = tmp_path / "forged-checkpoint-batch"
    first = run_batch(discovery, repository, cases, output)
    assert first["status"] == "COMPLETE"
    passed = first["units"][0]
    unit_directory = output / "units" / ready["id"]
    target = unit_directory / passed["target_path"]
    original = target.read_text(encoding="utf-8")
    assert original.count("+ 1") == 1
    forged = original.replace("+ 1", "+ 999")
    assert "+ 999" in forged
    target.write_text(forged, encoding="utf-8")
    checkpoint_entry = json.loads((output / CHECKPOINT_NAME).read_text(encoding="utf-8"))
    checkpoint_entry["target_sha256"] = "sha256:" + hashlib.sha256(forged.encode("utf-8")).hexdigest()
    (output / CHECKPOINT_NAME).write_text(
        json.dumps(checkpoint_entry, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (unit_directory / "route-evidence.json").unlink()

    second = run_batch(discovery, repository, cases, output)

    assert second["status"] == "COMPLETE"
    assert second["resumed_count"] == 0
    assert "+ 999" not in target.read_text(encoding="utf-8")
    assert (unit_directory / "route-evidence.json").is_file()

def test_batch_rejects_a_fresh_symlinked_units_directory(tmp_path: Path) -> None:
    repository = tmp_path / "fresh-symlink-repository"
    repository.mkdir()
    (repository / "value.py").write_text(
        "def value() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    discovery = discover_repository(
        plan_repository(repository, "local:fresh-units-symlink", "python", "typescript"),
        repository,
    )
    cases = tmp_path / "fresh-symlink-cases"
    cases.mkdir()
    (cases / "WU-00001.json").write_text('[{"args": [], "expected": 1}]\n')
    output = tmp_path / "fresh-symlink-batch"
    output.mkdir()
    external = tmp_path / "external-units"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    (output / "units").symlink_to(external, target_is_directory=True)

    with pytest.raises(RouteError, match="BATCH_UNITS_DIRECTORY_UNSAFE"):
        run_batch(discovery, repository, cases, output)

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(external.iterdir()) == [sentinel]

def test_batch_rejects_a_symlinked_checkpoint(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    output = tmp_path / "batch"
    output.mkdir()
    external = tmp_path / "external-checkpoint.jsonl"
    external.write_text("", encoding="utf-8")
    (output / CHECKPOINT_NAME).symlink_to(external)

    with pytest.raises(RouteError, match="BATCH_CHECKPOINT_UNSAFE"):
        run_batch(discovery, repository, tmp_path, output)

def test_batch_never_removes_a_symlinked_unit_directory_on_checkpoint_invalidation(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "value.py").write_text(
        "def value() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    discovery = discover_repository(
        plan_repository(repository, "local:symlink-checkpoint", "python", "typescript"),
        repository,
    )
    ready = discovery["results"][0]
    cases = tmp_path / "cases"
    cases.mkdir()
    case_path = cases / f"{ready['id']}.json"
    case_path.write_text('[{"args": [], "expected": 1}]\n', encoding="utf-8")
    output = tmp_path / "batch"
    first = run_batch(discovery, repository, cases, output)
    assert first["status"] == "COMPLETE"

    external = tmp_path / "must-survive"
    external.mkdir()
    sentinel = external / "sentinel.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    unit_directory = output / "units" / ready["id"]
    shutil.rmtree(unit_directory)
    unit_directory.symlink_to(external, target_is_directory=True)
    case_path.write_text('[{"args": [], "expected": 2}]\n', encoding="utf-8")

    with pytest.raises(RouteError, match="WORK_UNIT_OUTPUT_UNSAFE"):
        run_batch(discovery, repository, cases, output)
    assert sentinel.read_text(encoding="utf-8") == "preserve"

def test_batch_rejects_duplicate_or_unsafe_discovery_unit_ids(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    duplicate = json.loads(json.dumps(discovery))
    duplicate["results"][1]["id"] = duplicate["results"][0]["id"]
    with pytest.raises(RouteError, match="DISCOVERY_RESULT_ID_DUPLICATED"):
        run_batch(duplicate, repository, tmp_path, tmp_path / "duplicate-batch")

    unsafe = json.loads(json.dumps(discovery))
    unsafe["results"][0]["id"] = "../../escape"
    with pytest.raises(RouteError, match="DISCOVERY_RESULT_ID_INVALID"):
        run_batch(unsafe, repository, tmp_path, tmp_path / "unsafe-batch")
