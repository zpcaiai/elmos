"""Repository-scope pipeline: inventory -> discovery -> resumable batch."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import elmos_polyglot_route.discovery as discovery_module
from elmos_polyglot_route.batch import CHECKPOINT_NAME, UnitStatus, run_batch
from elmos_polyglot_route.discovery import Verdict, discover_repository, discover_unit, propose_candidates
from elmos_polyglot_route.models import Language, RouteError, SemanticIR
from elmos_polyglot_route.project_graph import build_project_graph
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


@pytest.mark.parametrize(
    ("language", "source", "expected"),
    [
        ("java", "public static long total(long value) { return value; }", ["total"]),
        ("python", "def total(value: int) -> int:\n    return value\n", ["total"]),
        ("csharp", "public static long Total(long value) { return value; }", ["Total"]),
        ("typescript", "export function total(value: number): number { return value; }", ["total"]),
        ("go", "package sample\nfunc total(value int64) int64 { return value }", ["total"]),
        ("rust", "pub fn total(value: i64) -> i64 { value }", ["total"]),
        ("cpp", "std::int64_t total(std::int64_t value) { return value; }", ["total"]),
        ("objc", "long long total(long long value) { return value; }", ["total"]),
        ("swift", "public func total(_ value: Int) -> Int { return value }", ["total"]),
    ],
)
def test_candidate_discovery_covers_every_repository_language(
    language: Language,
    source: str,
    expected: list[str],
) -> None:
    assert propose_candidates(source.encode("utf-8"), language) == expected


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

    monkeypatch.setattr(discovery_module, "analyze", fake_analyze)
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

    monkeypatch.setattr(discovery_module, "analyze", fail_second)
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


def test_batch_rejects_a_corrupt_checkpoint(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    discovery = discover_repository(_plan(repository), repository)
    output = tmp_path / "batch"
    output.mkdir(parents=True)
    (output / CHECKPOINT_NAME).write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(RouteError, match="BATCH_CHECKPOINT_CORRUPT"):
        run_batch(discovery, repository, tmp_path, output)


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


def test_batch_rejects_a_report_that_is_not_a_discovery_report(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    with pytest.raises(RouteError, match="DISCOVERY_REPORT_KIND_INVALID"):
        run_batch(_plan(repository), repository, tmp_path, tmp_path / "batch")
