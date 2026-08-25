from __future__ import annotations

import math
from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import Language
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.validation import validate, validate_source


def _javascript_source(name: str, value_type: str = "number") -> str:
    return (
        "/**\n"
        f" * @param {{{value_type}}} value\n"
        f" * @returns {{{value_type}}}\n"
        " */\n"
        f"export function {name}(value) {{ return value; }}\n"
    )


def _typescript_source(name: str) -> str:
    return f"export function {name}(value: number): number {{ return value; }}\n"


def _go_source(name: str, value_type: str = "float64") -> str:
    return f"package main\n\nfunc {name}(value {value_type}) {value_type} {{ return value }}\n"


def _assert_negative_zero(report: dict[str, object]) -> None:
    observations = report["observations"]
    assert isinstance(observations, list)
    assert len(observations) == 1
    observation = observations[0]
    assert isinstance(observation, dict)
    assert observation["encoding"] == "fp64-hex"
    assert observation["raw"] == "8000000000000000"
    value = observation["value"]
    assert isinstance(value, float)
    assert value == 0.0
    assert math.copysign(1.0, value) == -1.0


@pytest.mark.parametrize(
    ("name", "case_count"),
    [
        ("elmosHarnessFP64", 1),
        ("expected0", 1),
        ("actual1", 2),
    ],
)
def test_javascript_harness_aliases_the_subject_around_private_names(
    tmp_path: Path,
    name: str,
    case_count: int,
) -> None:
    source = tmp_path / f"{name}.mjs"
    source.write_text(_javascript_source(name, "integer"), encoding="utf-8")
    semantic = analyze(source, "javascript", name)
    function = semantic.functions[0]
    cases = [{"args": [index], "expected": index} for index in range(case_count)]

    source_report = validate_source(
        source,
        "javascript",
        function,
        cases,
        tmp_path / "source-runtime",
    )
    target_report = validate(
        emit(semantic, "javascript"),
        "javascript",
        function,
        cases,
        tmp_path / "target-runtime",
    )

    assert source_report["status"] == "PASSED"
    assert target_report["status"] == "PASSED"
    assert source_report["observations"] == target_report["observations"]


@pytest.mark.parametrize(
    ("name", "case_count"),
    [
        ("elmosHarnessFP64", 1),
        ("expected0", 1),
        ("actual1", 2),
    ],
)
def test_typescript_harness_aliases_the_subject_around_private_names(
    tmp_path: Path,
    name: str,
    case_count: int,
) -> None:
    source = tmp_path / f"{name}.ts"
    source.write_text(_typescript_source(name), encoding="utf-8")
    semantic = analyze(source, "typescript", name)
    function = semantic.functions[0]
    cases = [{"args": [float(index)], "expected": float(index)} for index in range(case_count)]

    source_report = validate_source(
        source,
        "typescript",
        function,
        cases,
        tmp_path / "source-runtime",
    )
    target_report = validate(
        emit(semantic, "typescript"),
        "typescript",
        function,
        cases,
        tmp_path / "target-runtime",
    )

    assert source_report["status"] == "PASSED"
    assert target_report["status"] == "PASSED"
    assert source_report["observations"] == target_report["observations"]


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [("typescript", "javascript"), ("javascript", "typescript")],
)
def test_typescript_javascript_routes_preserve_negative_zero_observations(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    suffix = ".ts" if source_language == "typescript" else ".mjs"
    source = tmp_path / f"identity{suffix}"
    source.write_text(
        _typescript_source("identity") if source_language == "typescript" else _javascript_source("identity"),
        encoding="utf-8",
    )
    semantic = analyze(source, source_language, "identity")
    function = semantic.functions[0]
    cases = [
        {"args": [-0.0], "expected": -0.0},
        {
            "args": [1.7976931348623157e308],
            "expected": 1.7976931348623157e308,
        },
        {"args": [5e-324], "expected": 5e-324},
    ]

    source_report = validate_source(
        source,
        source_language,
        function,
        cases,
        tmp_path / "source-runtime",
    )
    target_report = validate(
        emit(semantic, target_language),
        target_language,
        function,
        cases,
        tmp_path / "target-runtime",
    )

    for report in (source_report, target_report):
        observations = report["observations"]
        assert isinstance(observations, list)
        assert [observation["encoding"] for observation in observations] == [
            "fp64-hex",
            "fp64-hex",
            "fp64-hex",
        ]
        assert [observation["raw"] for observation in observations] == [
            "8000000000000000",
            "7fefffffffffffff",
            "0000000000000001",
        ]
    assert source_report["observations"] == target_report["observations"]


@pytest.mark.parametrize(
    ("source_language", "target_language"),
    [("go", "javascript"), ("javascript", "go")],
)
def test_go_javascript_routes_preserve_negative_zero_observations(
    tmp_path: Path,
    source_language: Language,
    target_language: Language,
) -> None:
    suffix = ".go" if source_language == "go" else ".mjs"
    source = tmp_path / f"identity{suffix}"
    source.write_text(
        _go_source("identity") if source_language == "go" else _javascript_source("identity"),
        encoding="utf-8",
    )
    semantic = analyze(source, source_language, "identity")
    function = semantic.functions[0]
    cases = [{"args": [-0.0], "expected": -0.0}]

    source_report = validate_source(
        source,
        source_language,
        function,
        cases,
        tmp_path / "source-runtime",
    )
    target_report = validate(
        emit(semantic, target_language),
        target_language,
        function,
        cases,
        tmp_path / "target-runtime",
    )

    _assert_negative_zero(source_report)
    _assert_negative_zero(target_report)
    assert source_report["observations"] == target_report["observations"]


def test_go_source_harness_aliases_imports_around_function_named_fmt(tmp_path: Path) -> None:
    source = tmp_path / "fmt.go"
    source.write_text(_go_source("fmt", "int64"), encoding="utf-8")
    semantic = analyze(source, "go", "fmt")

    report = validate_source(
        source,
        "go",
        semantic.functions[0],
        [{"args": [7], "expected": 7}],
        tmp_path / "source-runtime",
    )

    assert report["status"] == "PASSED"
    assert report["observations"][0]["value"] == 7
