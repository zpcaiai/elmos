"""Real Kotlin 2.2.20 analyzer, compiler, and runtime closure.

These tests intentionally use the exact standalone Kotlin distribution pinned
by ``toolchains._kotlin``.  A target-text assertion is not enough here: the
source PSI frontend must lift real Kotlin, emitted Kotlin must re-lift, and both
source and target must compile and execute under the pinned JDK/Kotlin tuple.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, target_ir_view
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.toolchains import (
    configured_polyglot_toolchain_root,
    exact_toolchain,
)
from elmos_polyglot_route.validation import validate, validate_source

ENGINE_ROOT = Path(__file__).resolve().parents[1]
KOTLIN_FIXTURE = ENGINE_ROOT / "fixtures" / "kotlin" / "pricing.kt"
CASES = [
    {"args": [10, 2], "expected": 12},
    {"args": [-1, 2], "expected": 0},
]
EXPECTED_KOTLIN_VERSION = {
    "homebrew": "kotlinc-jvm 2.2.20 (JRE 21.0.11)",
    "temurin": "kotlinc-jvm 2.2.20 (JRE 21.0.11+10-LTS)",
}[os.environ.get("ELMOS_JAVA21_DISTRIBUTION", "homebrew")]


def test_kotlin_uses_the_exact_standalone_2_2_20_jdk21_tuple() -> None:
    toolchain = exact_toolchain("kotlin")
    active_java_home = Path(exact_toolchain("java").executable).parents[1]

    assert toolchain.language == "kotlin"
    assert toolchain.version == EXPECTED_KOTLIN_VERSION
    kotlin_root = configured_polyglot_toolchain_root() / "kotlin" / "2.2.20"
    assert toolchain.executable == str(kotlin_root / "bin" / "kotlinc")
    assert toolchain.auxiliary == str(kotlin_root / "bin" / "kotlin")
    assert toolchain.executable_sha256 == (
        "90750c977cc043dd2b05c69dd4e052c10377554925dd5a155e74ef732be28c7d"
    )
    assert "kotlin-build-number=2.2.20-release-333" in toolchain.profile
    assert (
        "kotlin-compiler-jar-sha256="
        "8546feb440ec2d59e00d475936523fcd3f528e21c7e8eb8a95e6de5044a6d496"
    ) in toolchain.profile
    assert (
        "kotlin-stdlib-jar-sha256="
        "8836ccffd3585fadda9901244b20d42901d2f3cd581058d8434e2ffabcf3a3e7"
    ) in toolchain.profile
    assert f"kotlin-jvm-home={active_java_home}" in toolchain.profile
    # Exact availability and real local execution are not a proof of the
    # compiler/runtime implementation itself.
    assert "kotlin-runtime-semantic-soundness=NOT_RUN" in toolchain.profile


def test_kotlin_psi_analyzer_relift_and_real_source_target_runtime(tmp_path: Path) -> None:
    semantic = analyze(KOTLIN_FIXTURE, "kotlin", "calculate")

    assert semantic.source_language == "kotlin"
    assert semantic.analyzer == "kotlin-compiler PSI"
    assert semantic.analyzer_version == "2.2.20"
    assert semantic.functions[0].name == "calculate"

    identifier_plan = plan_identifiers(semantic, "kotlin")
    target_view = target_ir_view(semantic, identifier_plan)
    emitted = emit(semantic, "kotlin", identifier_plan=identifier_plan)
    assert "Math.addExact(subtotal, tax)" in emitted.content

    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    relifted = analyze(
        target,
        "kotlin",
        target_view.functions[0].name,
        emitted_target=True,
    )
    assert [function.semantic_mapping() for function in relifted.functions] == [
        function.semantic_mapping() for function in target_view.functions
    ]

    source_report = validate_source(
        KOTLIN_FIXTURE,
        "kotlin",
        semantic.functions[0],
        CASES,
        tmp_path / "source-runtime",
    )
    target_report = validate(
        emitted,
        "kotlin",
        target_view.functions[0],
        CASES,
        tmp_path / "target-runtime",
    )
    assert source_report["status"] == "PASSED"
    assert target_report["status"] == "PASSED"
    assert source_report["observations"] == target_report["observations"]


def test_kotlin_psi_analyzer_lifts_explicit_immutable_local(tmp_path: Path) -> None:
    source = tmp_path / "local.kt"
    source.write_text(
        "fun adjusted(value: Long): Long {\n"
        "    val increment: Long = 2L\n"
        "    return value + increment\n"
        "}\n",
        encoding="utf-8",
    )

    semantic = analyze(source, "kotlin", "adjusted")
    assert semantic.functions[0].body[0].to_mapping() == {
        "kind": "let",
        "name": "increment",
        "type": "integer",
        "expression": {"kind": "literal", "value": 2},
    }

    identifier_plan = plan_identifiers(semantic, "kotlin")
    target_view = target_ir_view(semantic, identifier_plan)
    emitted = emit(semantic, "kotlin", identifier_plan=identifier_plan)
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    relifted = analyze(target, "kotlin", target_view.functions[0].name, emitted_target=True)
    assert [function.semantic_mapping() for function in relifted.functions] == [
        function.semantic_mapping() for function in target_view.functions
    ]


def test_kotlin_int_is_rejected_instead_of_widened_silently(tmp_path: Path) -> None:
    source = tmp_path / "narrow.kt"
    source.write_text(
        "fun identity(value: Int): Int {\n"
        "    return value\n"
        "}\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match=r"^KOTLIN_UNSUPPORTED_TYPE:Int$"):
        analyze(source, "kotlin", "identity")


def test_kotlin_named_function_selection_rejects_zero_matches_explicitly(
    tmp_path: Path,
) -> None:
    source = tmp_path / "missing.kt"
    source.write_text(
        "fun present(value: Long): Long {\n"
        "    return value\n"
        "}\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match=r"FUNCTION_NOT_FOUND:absent"):
        analyze(source, "kotlin", "absent")


def test_kotlin_named_function_selection_rejects_overloads_instead_of_using_source_order(
    tmp_path: Path,
) -> None:
    source = tmp_path / "overloaded.kt"
    source.write_text(
        "fun calculate(value: Long): Long {\n"
        "    return value\n"
        "}\n\n"
        "fun calculate(left: Long, right: Long): Long {\n"
        "    return left + right\n"
        "}\n",
        encoding="utf-8",
    )

    with pytest.raises(RouteError, match=r"^KOTLIN_FUNCTION_NAME_AMBIGUOUS$"):
        analyze(source, "kotlin", "calculate")
