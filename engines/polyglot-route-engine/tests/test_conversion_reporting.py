from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

import elmos_polyglot_route.conversion_reporting as conversion_reporting_module
from elmos_polyglot_route.conversion_reporting import (
    JSON_REPORT_NAME,
    MARKDOWN_REPORT_NAME,
    build_conversion_report,
    normalize_reason_code,
    reset_conversion_report_outputs,
    validate_conversion_report,
    write_conversion_reports,
)
from elmos_polyglot_route.models import RouteError

SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "project-conversion-schema"
    / "project-conversion-report.schema.json"
)


def _assert_schema(report: dict[str, object]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)


def _assert_related_schema(name: str, value: dict[str, object]) -> None:
    main = json.loads(SCHEMA.read_text(encoding="utf-8"))
    schema = json.loads((SCHEMA.parent / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    registry = Registry().with_resource(main["$id"], Resource.from_contents(main))
    Draft202012Validator(schema, registry=registry).validate(value)


def _sha(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _discovery(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "kind": "elmos.repository-discovery-report",
        "repository_ref": "local:conversion-report-fixture",
        "snapshot_sha256": "a" * 64,
        "route_id": "python-to-typescript",
        "source_language": "python",
        "target_language": "typescript",
        "profile": "typed-pure-function-v1",
        "results": results,
    }


def _batch(units: list[dict[str, object]]) -> dict[str, object]:
    return {"kind": "elmos.repository-batch-report", "units": units}


def _write_target(batch_output: Path, unit_id: str, content: str) -> dict[str, object]:
    root = batch_output / "units" / unit_id
    root.mkdir(parents=True)
    (root / "migrated.ts").write_text(content, encoding="utf-8")
    return {
        "id": unit_id,
        "status": "PASSED",
        "function_name": "add",
        "target_path": "migrated.ts",
        "target_sha256": f"sha256:{_sha(content)}",
        "evidence_path": f"units/{unit_id}/route-evidence.json",
    }


def test_atomic_report_and_bundle_writes_do_not_follow_preseeded_temp_symlinks(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    victim = tmp_path / "victim"
    report_temp = output / f"{JSON_REPORT_NAME}.tmp"
    report_temp.symlink_to(victim)

    descriptor = conversion_reporting_module._atomic_write(output / JSON_REPORT_NAME, b"{}\n")
    assert descriptor["bytes"] == 3
    assert (output / JSON_REPORT_NAME).read_bytes() == b"{}\n"
    assert report_temp.is_symlink()
    assert not victim.exists()

    payload = b"evidence"
    source = output / "evidence.txt"
    source.write_bytes(payload)
    bundle_temp = output / f"{conversion_reporting_module.REPORT_BUNDLE_NAME}.tmp"
    bundle_temp.symlink_to(victim)
    bundle = conversion_reporting_module._write_bundle(
        output,
        [{"path": source.name, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}],
        "sha256:" + "a" * 64,
    )
    assert bundle["bytes"] > 0
    assert (output / conversion_reporting_module.REPORT_BUNDLE_NAME).is_file()
    assert bundle_temp.is_symlink()
    assert not victim.exists()


def test_report_read_rejects_an_oversized_file_before_buffering(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as handle:
        handle.truncate(1_025)
    with pytest.raises(RouteError, match="REPORT_TEST_TOO_LARGE"):
        conversion_reporting_module._stable_bytes(oversized, "REPORT_TEST", max_bytes=1_024)


def test_verified_function_report_is_content_addressed_and_markdown_is_derived(
    tmp_path: Path,
) -> None:
    source = "def add(left: int, right: int) -> int:\n    return left + right\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(source, encoding="utf-8")
    target = "export function add(left: number, right: number): number {\n  return left + right;\n}\n"
    batch_output = tmp_path / "batch"
    unit = _write_target(batch_output, "WU-00001", target)
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "math.py",
                    "observed_sha256": _sha(source),
                    "verdict": "READY",
                    "candidates": ["add"],
                    "function_name": "add",
                }
            ]
        ),
        _batch([unit]),
        repository,
        batch_output,
        build_status="PASSED",
    )

    assert report["status"] == "COMPLETE"
    _assert_schema(report)
    assert report["metric"] == {
        "definition_id": "verified-functional-obligation-success-rate/v1",
        "measurement_unit": "FUNCTIONAL_OBLIGATION",
        "comparison_basis": "DECLARED_BEHAVIOR_ORACLE",
        "numerator": 1,
        "denominator": 1,
        "exact_fraction": "1/1",
        "success_rate_basis_points": 10000,
        "display_percent": "100.00%",
        "measurement_status": "MEASURED",
        "denominator_complete": True,
        "reported_obligation_count": 1,
        "unknown_scope_count": 0,
        "unreported_obligation_count": 0,
        "project_success_rate_lower_bound_basis_points": 10000,
        "project_success_rate_upper_bound_basis_points": 10000,
        "project_success_rate_display": "100.00%",
        "formula": "VERIFIED functional obligations / compiler-completely inventoried functional obligations",
    }
    assert report["evidence_boundary"]["target_behavior_oracle"] == "PASSED_PER_VERIFIED_FUNCTION"
    assert (
        report["evidence_boundary"]["source_target_declared_case_equivalence"]
        == "PASSED_PER_VERIFIED_FUNCTION"
    )
    function = report["functions"][0]
    assert function["mapping"]["confidence"] == 0.7
    assert function["source_blocks"][0]["extraction_method"] == "PYTHON_AST_FUNCTION"
    assert function["target_blocks"][0]["extraction_method"] == "NAME_ANCHORED_DOCUMENT_EXCERPT"
    output = tmp_path / "output"
    output.mkdir()
    summary = write_conversion_reports(report, output)
    assert summary["verified_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["code_artifact_ready"] is True
    assert len(summary["json_report"]["sha256"]) == 64
    assert len(summary["markdown_report"]["sha256"]) == 64
    assert report["markdown_sha256"] == summary["markdown_report"]["sha256"]
    markdown = (output / MARKDOWN_REPORT_NAME).read_text(encoding="utf-8")
    assert "1/1 = 100.00%" in markdown
    assert "源/目标运行时等价仍为 NOT_RUN" in markdown
    assert "- 路径：`math.py`" in markdown
    assert f"- 代码块 SHA-256：`{_sha(source)}`" in markdown
    assert f"- 文档 SHA-256：`{_sha(source)}`" in markdown
    assert "- 范围精度：`EXACT_DECLARATION_RANGE`" in markdown
    assert "- 范围精度：`APPROXIMATE_NAME_ANCHORED_RANGE`" in markdown
    assert "映射置信度：`0.70`（`APPROXIMATE`）" in markdown
    assert json.loads((output / JSON_REPORT_NAME).read_text()) == report

    report["markdown_sha256"] = "0" * 64
    with pytest.raises(RouteError, match="MARKDOWN_DIGEST_MISMATCH"):
        write_conversion_reports(report, tmp_path / "tampered-output")


def test_reason_codes_are_normalized_to_the_shared_three_to_120_character_contract() -> None:
    assert normalize_reason_code("ABC") == "ABC"
    assert normalize_reason_code("A" + "B" * 119) == "A" + "B" * 119
    assert normalize_reason_code("AB") == "FUNCTION_CONVERSION_FAILED"
    assert normalize_reason_code("A" + "B" * 120) == "FUNCTION_CONVERSION_FAILED"


def test_document_level_excerpt_never_claims_mapping_confidence(tmp_path: Path) -> None:
    source = "def add(value: int) -> int:\n    return value\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(source, encoding="utf-8")
    target = "export const generated = (value: number): number => value;\n"
    batch_output = tmp_path / "batch"
    unit = _write_target(batch_output, "WU-00001", target)
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "math.py",
                    "observed_sha256": _sha(source),
                    "verdict": "READY",
                    "candidates": ["add"],
                    "function_name": "add",
                }
            ]
        ),
        _batch([unit]),
        repository,
        batch_output,
        build_status="PASSED",
    )

    _assert_schema(report)
    function = report["functions"][0]
    assert function["status"] == "VERIFIED"
    assert function["target_blocks"][0]["extraction_method"] == "DOCUMENT_PREFIX_EXCERPT"
    assert function["mapping"]["kind"] == "SYNTHESIZED"
    assert function["mapping"]["confidence"] == 0.0
    output = tmp_path / "output"
    write_conversion_reports(report, output)
    markdown = (output / MARKDOWN_REPORT_NAME).read_text(encoding="utf-8")
    assert "- 范围精度：`UNMAPPED_DOCUMENT_RANGE`" in markdown
    assert "映射置信度：`0.00`（`UNMAPPED`）" in markdown

    function["mapping"]["confidence"] = 1.0
    with pytest.raises(RouteError, match="FUNCTION_REPORT_MAPPING_INVALID"):
        validate_conversion_report(report)


def test_global_snippet_budget_omission_keeps_exact_block_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = "def add(left: int, right: int) -> int:\n    return left + right\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(source, encoding="utf-8")
    target = "export function add(left: number, right: number): number {\n  return left + right;\n}\n"
    batch_output = tmp_path / "batch"
    unit = _write_target(batch_output, "WU-00001", target)
    monkeypatch.setattr(conversion_reporting_module, "MAX_SNIPPET_BUDGET_BYTES", 0)

    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "math.py",
                    "observed_sha256": _sha(source),
                    "verdict": "READY",
                    "candidates": ["add"],
                    "function_name": "add",
                }
            ]
        ),
        _batch([unit]),
        repository,
        batch_output,
        build_status="PASSED",
    )
    _assert_schema(report)
    source_block = report["functions"][0]["source_blocks"][0]
    target_block = report["functions"][0]["target_blocks"][0]
    assert source_block["snippet"] is None
    assert source_block["omission_reason"] == "GLOBAL_SNIPPET_BUDGET_EXCEEDED"
    assert source_block["range"]["start_byte"] == 0
    assert source_block["range"]["end_byte"] == len(source.encode("utf-8"))
    assert source_block["block_sha256"] == _sha(source)
    assert source_block["document_sha256"] == _sha(source)
    assert target_block["snippet"] is None
    assert target_block["range"]["end_byte"] == len(target.encode("utf-8"))
    assert target_block["block_sha256"] == _sha(target)

    output = tmp_path / "output"
    write_conversion_reports(report, output)
    markdown = (output / MARKDOWN_REPORT_NAME).read_text(encoding="utf-8")
    assert "- 路径：`math.py`" in markdown
    assert f"- 字节范围：`0..{len(source.encode('utf-8'))}`" in markdown
    assert f"- 代码块 SHA-256：`{_sha(source)}`" in markdown
    assert "NOT_EMBEDDED: GLOBAL_SNIPPET_BUDGET_EXCEEDED" in markdown


def test_non_utf8_block_omission_keeps_exact_block_identity(tmp_path: Path) -> None:
    source = b"int f(int value) { return \xff; }\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "raw.cpp").write_bytes(source)
    discovery = _discovery(
        [
            {
                "id": "WU-00001",
                "source_path": "raw.cpp",
                "observed_sha256": hashlib.sha256(source).hexdigest(),
                "verdict": "UNSUPPORTED",
                "reason": "CPP_PARSE_FAILED",
                "candidate_enumeration_complete": True,
                "candidates": ["f"],
                "rejected_candidates": [{"candidate": "f", "reason": "CPP_PARSE_FAILED"}],
            }
        ]
    )
    discovery["route_id"] = "cpp-to-typescript"
    discovery["source_language"] = "cpp"
    report = build_conversion_report(
        discovery,
        _batch([{"id": "WU-00001", "status": "SKIPPED_NOT_READY", "reason_code": "CPP_PARSE_FAILED"}]),
        repository,
        tmp_path / "batch",
        build_status="NOT_RUN",
    )

    _assert_schema(report)
    block = report["functions"][0]["source_blocks"][0]
    assert block["snippet"] is None
    assert block["omission_reason"] == "SOURCE_NOT_UTF8"
    assert block["range"] == {
        "start_byte": 0,
        "end_byte": len(source),
        "start_line": 1,
        "start_column": 1,
        "end_line": 2,
        "end_column": 1,
    }
    assert block["block_sha256"] == hashlib.sha256(source).hexdigest()
    assert block["document_sha256"] == hashlib.sha256(source).hexdigest()


def test_multiple_functions_and_rejected_candidates_never_shrink_the_denominator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (
        "def add(value: int, step: int) -> int:\n    return value + step\n\ndef unsupported(value):\n    return value\n"
    )
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "mixed.py").write_text(source, encoding="utf-8")
    target = "export function add(value: number, step: number): number {\n  return value + step;\n}\n"
    batch_output = tmp_path / "batch"
    unit = _write_target(batch_output, "WU-00001", target)
    parse_calls = 0
    real_parse = conversion_reporting_module.ast.parse

    def counted_parse(*args: object, **kwargs: object) -> object:
        nonlocal parse_calls
        parse_calls += 1
        return real_parse(*args, **kwargs)

    monkeypatch.setattr(conversion_reporting_module.ast, "parse", counted_parse)
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "mixed.py",
                    "observed_sha256": _sha(source),
                    "verdict": "READY",
                    "candidates": ["add", "unsupported"],
                    "function_name": "add",
                    "rejected_candidates": [
                        {"candidate": "unsupported", "reason": "PYTHON_PARAMETER_TYPE_REQUIRED:value"}
                    ],
                }
            ]
        ),
        _batch([unit]),
        repository,
        batch_output,
        build_status="PASSED",
    )

    assert report["status"] == "PARTIAL"
    _assert_schema(report)
    assert report["metric"]["numerator"] == 1
    assert report["metric"]["denominator"] == 2
    assert report["metric"]["success_rate_basis_points"] == 5000
    assert report["status_counts"] == {"VERIFIED": 1, "UNSUPPORTED": 1}
    assert (
        report["evidence_boundary"]["source_target_declared_case_equivalence"]
        == "PASSED_PER_VERIFIED_FUNCTION"
    )
    failed = report["functions"][1]
    assert failed["failure"]["reason_code"] == "PYTHON_PARAMETER_TYPE_REQUIRED"
    assert failed["target_blocks"] == []
    assert failed["improvement_actions"]
    assert parse_calls == 1


def test_incomplete_declaration_inventory_adds_an_unknown_obligation(tmp_path: Path) -> None:
    source = "def add(value: int) -> int:\n    return value\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(source, encoding="utf-8")
    target = "export function add(value: number): number { return value; }\n"
    batch_output = tmp_path / "batch"
    unit = _write_target(batch_output, "WU-00001", target)
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "math.py",
                    "observed_sha256": _sha(source),
                    "verdict": "READY",
                    "candidates": ["add"],
                    "function_name": "add",
                    "candidate_enumeration_complete": False,
                    "candidate_enumeration_reason": "DECLARATION_SCAN_NOT_COMPILER_COMPLETE",
                }
            ]
        ),
        _batch([unit]),
        repository,
        batch_output,
        build_status="PASSED",
    )

    assert report["status"] == "PARTIAL"
    _assert_schema(report)
    assert report["metric"]["exact_fraction"] == "1/1"
    assert report["metric"]["denominator_complete"] is False
    assert report["evidence_boundary"]["target_behavior_oracle"] == "PASSED_PER_VERIFIED_FUNCTION"
    assert (
        report["evidence_boundary"]["source_target_declared_case_equivalence"]
        == "PASSED_PER_VERIFIED_FUNCTION"
    )
    assert report["metric"]["measurement_status"] == "INDETERMINATE"
    assert report["metric"]["reported_obligation_count"] == 2
    assert report["metric"]["unknown_scope_count"] == 1
    assert report["metric"]["project_success_rate_display"] == "0.00%–100.00% (INDETERMINATE)"
    assert report["functions"][1]["kind"] == "UNKNOWN_SOURCE_UNIT"
    assert report["functions"][1]["failure"]["stage"] == "INVENTORY"


def test_two_of_three_uses_floor_basis_points_and_behavior_failure_keeps_target(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    batch_output = tmp_path / "batch"
    results: list[dict[str, object]] = []
    units: list[dict[str, object]] = []
    for index, name in enumerate(("one", "two", "three"), start=1):
        source = f"def {name}(value: int) -> int:\n    return value\n"
        (repository / f"{name}.py").write_text(source, encoding="utf-8")
        unit_id = f"WU-{index:05d}"
        results.append(
            {
                "id": unit_id,
                "source_path": f"{name}.py",
                "observed_sha256": _sha(source),
                "verdict": "READY",
                "candidates": [name],
                "function_name": name,
            }
        )
        target = f"export function {name}(value: number): number {{ return value; }}\n"
        unit = _write_target(batch_output, unit_id, target)
        unit["function_name"] = name
        if name == "three":
            unit.update(
                status="FAILED",
                reason_code="TARGET_VALIDATION_FAILED",
                reason="TARGET_VALIDATION_FAILED:behavior mismatch",
                failure_stage="BEHAVIOR_REPLAY",
            )
        units.append(unit)

    report = build_conversion_report(
        _discovery(results),
        _batch(units),
        repository,
        batch_output,
        build_status="PASSED",
    )
    assert report["metric"]["exact_fraction"] == "2/3"
    _assert_schema(report)
    assert report["metric"]["success_rate_basis_points"] == 6666
    assert report["metric"]["display_percent"] == "66.66%"
    failed = report["functions"][2]
    assert failed["status"] == "FAILED"
    assert failed["target_blocks"][0]["snippet"].startswith("export function three")
    output = tmp_path / "output"
    output.mkdir()
    write_conversion_reports(report, output)
    markdown = (output / MARKDOWN_REPORT_NAME).read_text(encoding="utf-8")
    assert "目标代码块" in markdown
    assert "TARGET_VALIDATION_FAILED" in markdown


def test_zero_percent_unknown_scope_is_downloadable_but_not_code_ready(tmp_path: Path) -> None:
    source = "# ``` must not close the report fence\nVALUE = 1\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "constants.py").write_text(source, encoding="utf-8")
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "constants.py",
                    "observed_sha256": _sha(source),
                    "verdict": "NO_CANDIDATE_DECLARATION",
                    "reason": (
                        "NO_CANDIDATE_DECLARATION\n![track](https://evil.example/pixel) "
                        "<script>alert(`x`)</script> 🧪\u0001"
                    ),
                    "candidates": [],
                }
            ]
        ),
        _batch(
            [
                {
                    "id": "WU-00001",
                    "status": "SKIPPED_NOT_READY",
                    "reason_code": "NO_CANDIDATE_DECLARATION",
                }
            ]
        ),
        repository,
        tmp_path / "batch",
        build_status="NOT_RUN",
    )
    assert report["status"] == "BLOCKED"
    _assert_schema(report)
    assert report["metric"]["exact_fraction"] == "0/0"
    assert report["metric"]["display_percent"] == "0.00%"
    assert report["metric"]["denominator_complete"] is False
    assert report["metric"]["project_success_rate_display"] == "0.00%–100.00% (INDETERMINATE)"
    output = tmp_path / "output"
    output.mkdir()
    summary = write_conversion_reports(report, output)
    assert summary["code_artifact_ready"] is False
    assert summary["failure_summary_count"] == 1
    assert summary["failure_summaries"][0]["obligation_id"] == "WU-00001:FO-001"
    markdown = (output / MARKDOWN_REPORT_NAME).read_text(encoding="utf-8")
    assert "NOT_GENERATED" in markdown
    assert "````python" in markdown
    assert "![track](" not in markdown
    assert "<script>" not in markdown
    assert "＜script＞" in markdown
    assert "🧪" in markdown
    assert "\u0001" not in markdown
    json_report = json.loads((output / JSON_REPORT_NAME).read_text(encoding="utf-8"))
    assert "<script>" in json_report["functions"][0]["failure"]["description"]
    assert "N/A (NO_REPORTED_CALLABLE_DENOMINATOR)" in markdown
    assert "0/0` = `0.00%" not in markdown


def test_report_rejects_source_or_metric_drift(tmp_path: Path) -> None:
    source = "def add(value: int) -> int:\n    return value\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(source, encoding="utf-8")
    batch_output = tmp_path / "batch"
    unit = _write_target(batch_output, "WU-00001", "export function add(value: number) { return value; }\n")
    discovery = _discovery(
        [
            {
                "id": "WU-00001",
                "source_path": "math.py",
                "observed_sha256": _sha(source),
                "verdict": "READY",
                "candidates": ["add"],
                "function_name": "add",
            }
        ]
    )
    report = build_conversion_report(
        discovery,
        _batch([unit]),
        repository,
        batch_output,
        build_status="PASSED",
    )
    missing_target_digest = dict(unit)
    missing_target_digest.pop("target_sha256")
    with pytest.raises(RouteError, match="TARGET_DIGEST_MISSING_OR_INVALID"):
        build_conversion_report(
            discovery,
            _batch([missing_target_digest]),
            repository,
            batch_output,
            build_status="PASSED",
        )

    report["metric"]["numerator"] = 0
    with pytest.raises(RouteError, match="METRIC_INCONSISTENT"):
        validate_conversion_report(report)

    (repository / "math.py").write_text(source + "# drift\n", encoding="utf-8")
    with pytest.raises(RouteError, match="SOURCE_DIGEST_MISMATCH"):
        build_conversion_report(
            discovery,
            _batch([unit]),
            repository,
            batch_output,
            build_status="PASSED",
        )


def test_long_source_identifier_and_signature_are_content_addressed_within_schema_limits(
    tmp_path: Path,
) -> None:
    symbol = "function_" + "x" * 260
    parameters = ", ".join(f"parameter_{index}_{'y' * 20}: int" for index in range(80))
    source = f"def {symbol}({parameters}) -> int:\n    return 1\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "long.py").write_text(source, encoding="utf-8")
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "long.py",
                    "observed_sha256": _sha(source),
                    "verdict": "UNSUPPORTED",
                    "reason": "PYTHON_PARAMETER_COUNT_OUTSIDE_PROFILE",
                    "candidates": [symbol],
                    "rejected_candidates": [
                        {
                            "candidate": symbol,
                            "reason": "PYTHON_PARAMETER_COUNT_OUTSIDE_PROFILE",
                        }
                    ],
                }
            ]
        ),
        _batch(
            [
                {
                    "id": "WU-00001",
                    "status": "SKIPPED_NOT_READY",
                    "reason_code": "UNSUPPORTED",
                }
            ]
        ),
        repository,
        tmp_path / "batch",
        build_status="NOT_RUN",
    )

    _assert_schema(report)
    function = report["functions"][0]
    assert len(function["source_blocks"][0]["symbol_id"]) <= 200
    assert "sha256:" in function["source_blocks"][0]["symbol_id"]
    assert len(function["functional_description"]["text"]) <= 1_000
    assert "sha256:" in function["functional_description"]["text"]


def test_large_report_is_sharded_without_omission_or_metric_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names = [f"function_{index}" for index in range(6)]
    source = "\n".join(f"def {name}(value: int) -> int:\n    return value" for name in names) + "\n"
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "many.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr(conversion_reporting_module, "MAX_OBLIGATIONS_PER_SHARD", 2)
    monkeypatch.setattr(conversion_reporting_module, "MAX_SNIPPET_BUDGET_BYTES", 0)
    report = build_conversion_report(
        _discovery(
            [
                {
                    "id": "WU-00001",
                    "source_path": "many.py",
                    "observed_sha256": _sha(source),
                    "verdict": "UNSUPPORTED",
                    "reason": "MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION",
                    "candidates": names,
                    "rejected_candidates": [{"candidate": name, "reason": "PARTITION_REQUIRED"} for name in names],
                }
            ]
        ),
        _batch(
            [
                {
                    "id": "WU-00001",
                    "status": "SKIPPED_NOT_READY",
                    "reason_code": "UNSUPPORTED",
                }
            ]
        ),
        repository,
        tmp_path / "batch",
        build_status="NOT_RUN",
    )

    _assert_schema(report)
    assert len(report["functions"]) == 6
    assert report["metric"]["unreported_obligation_count"] == 0
    assert report["metric"]["measurement_status"] == "MEASURED"
    assert report["metric"]["project_success_rate_lower_bound_basis_points"] == 0
    assert report["metric"]["project_success_rate_upper_bound_basis_points"] == 0
    output = tmp_path / "output"
    summary = write_conversion_reports(report, output)
    assert summary["storage_mode"] == "SHARDED"
    assert summary["shard_count"] == 3
    assert summary["unreported_obligation_count"] == 0
    assert summary["report_bundle"]["path"] == "FUNCTION_CONVERSION_REPORT_BUNDLE.zip"
    index = json.loads((output / JSON_REPORT_NAME).read_text(encoding="utf-8"))
    _assert_related_schema("project-conversion-report-index.schema.json", index)
    assert index["kind"] == "elmos.project-language-conversion-report-index"
    assert index["shard_count"] == 3
    assert sum(item["function_count"] for item in index["shards"]) == 6
    observed: list[str] = []
    for descriptor in index["shards"]:
        shard = json.loads((output / descriptor["json"]["path"]).read_text(encoding="utf-8"))
        _assert_related_schema("project-conversion-report-shard.schema.json", shard)
        observed.extend(item["obligation_id"] for item in shard["functions"])
        assert all(item["source_blocks"][0]["snippet"] is None for item in shard["functions"])
        assert all(item["source_blocks"][0]["range"] is not None for item in shard["functions"])
        assert all(item["source_blocks"][0]["block_sha256"] for item in shard["functions"])
        assert sum(shard["shard"]["status_counts"].values()) == shard["shard"]["function_count"]
        assert shard["metric"] == report["metric"]
    assert observed == [item["obligation_id"] for item in report["functions"]]
    assert len(observed) == len(set(observed))
    bundle_manifest = json.loads(
        (output / "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json").read_text(encoding="utf-8")
    )
    _assert_related_schema("project-conversion-report-bundle-manifest.schema.json", bundle_manifest)
    reset_conversion_report_outputs(output)
    assert not (output / JSON_REPORT_NAME).exists()
    assert not (output / MARKDOWN_REPORT_NAME).exists()
    assert not (output / "functional-conversion-report-shards").exists()
    assert not (output / "FUNCTION_CONVERSION_REPORT_BUNDLE.zip").exists()
    assert not (output / "FUNCTION_CONVERSION_REPORT_BUNDLE_MANIFEST.json").exists()
