from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

import elmos_polyglot_route.discovery as discovery_module
from elmos_polyglot_route.cli import main
from elmos_polyglot_route.preflight import preflight_identity, repository_preflight


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



SCHEMA = (
    Path(__file__).resolve().parents[3]
    / "contracts"
    / "project-conversion-schema"
    / "repository-conversion-preflight.schema.json"
)


def _assert_schema(report: dict[str, object]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(report)


def _run_cli(repository: Path, output: Path) -> int:
    return main(
        [
            "repository-preflight",
            "--repository",
            str(repository),
            "--repository-ref",
            "local:preflight-fixture",
            "--source-language",
            "python",
            "--target-language",
            "typescript",
            "--output",
            str(output),
        ]
    )


def test_repository_preflight_counts_within_limit_without_native_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.py").write_text(
        "def add(left: int, right: int) -> int:\n    return left + right\n",
        encoding="utf-8",
    )

    def native_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("repository-preflight invoked native analysis")

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(native_must_not_run))
    output = tmp_path / "preflight.json"
    assert _run_cli(repository, output) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    _assert_schema(report)
    assert report["status"] == "PASSED"
    assert report["reason_code"] is None
    assert report["obligation_count"] == 1
    assert report["obligation_count_semantics"] == "EXACT_REPORTED_ROWS"
    assert report["actual_obligation_count"] == 1
    assert report["obligation_limit"] == 10_000
    assert report["count_complete"] is True
    assert report["execution_status"] == "NOT_RUN"
    assert report["certification_status"] == "NOT_CERTIFIED"
    assert report["preflight_id"] == preflight_identity(report)


def test_repository_preflight_rejects_at_the_bounded_10001_sentinel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = "\n".join(
        f"def function_{index}(value: int) -> int:\n    return value"
        for index in range(10_001)
    )
    (repository / "many.py").write_text(source + "\n", encoding="utf-8")

    def native_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("repository-preflight invoked native analysis")

    monkeypatch.setattr(discovery_module, "analyze_many", _as_analyze_many(native_must_not_run))
    output = tmp_path / "preflight.json"
    assert _run_cli(repository, output) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    _assert_schema(report)
    assert report["status"] == "REJECTED"
    assert report["reason_code"] == "FUNCTIONAL_OBLIGATION_LIMIT_EXCEEDED"
    assert report["obligation_count"] == 10_001
    assert report["obligation_count_semantics"] == "REPORTED_ROW_LOWER_BOUND"
    assert report["actual_obligation_count"] is None
    assert report["count_complete"] is False
    assert report["preflight_id"] == preflight_identity(report)


def test_non_python_preflight_never_claims_a_complete_actual_inventory(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "math.cpp").write_text(
        "int add(int left, int right) { return left + right; }\n",
        encoding="utf-8",
    )

    report = repository_preflight(
        repository,
        "local:cpp-preflight-fixture",
        "cpp",
        "python",
    )
    _assert_schema(report)
    assert report["status"] == "PASSED_WITH_INCOMPLETE_INVENTORY"
    assert report["reason_code"] is None
    assert report["count_complete"] is False
    assert report["obligation_count"] == 2
    assert report["reported_obligation_lower_bound"] == 2
    assert report["obligation_count_semantics"] == "REPORTED_ROW_LOWER_BOUND"
    assert report["actual_obligation_count"] is None
    assert report["actual_obligation_count_status"] == "UNKNOWN"
    assert report["preflight_id"] == preflight_identity(report)
