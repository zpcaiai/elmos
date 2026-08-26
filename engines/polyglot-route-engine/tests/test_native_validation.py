from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

import pytest

import elmos_polyglot_route.native as native
import elmos_polyglot_route.validation as validation
from elmos_polyglot_route.emitter import (
    _CPP_HELPERS,
    _OBJC_HELPERS,
    _SWIFT_HELPERS,
    EmittedFile,
    emit,
)
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, target_ir_view
from elmos_polyglot_route.models import Function, Language, RouteError, SemanticIR
from elmos_polyglot_route.native import analyze, inventory_module
from elmos_polyglot_route.toolchains import ExactToolchain, exact_toolchain
from elmos_polyglot_route.validation import (
    _PROCESS_DIAGNOSTIC_LIMIT,
    _bounded_process_diagnostic,
    _cpp_harness,
    _java_harness,
    _objc_harness,
    _python_harness,
    _python_literal,
    _run,
    _swift_harness,
    validate,
    validate_source,
)

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _failing_receipt_bound_swift_analyzer(
    tmp_path: Path,
    stderr: str,
) -> tuple[Path, dict[str, object]]:
    if "'" in stderr:
        raise AssertionError("test stderr must remain shell-literal safe")
    source = tmp_path / "source-ElmosSwiftAnalyzer"
    source.write_text(
        f"#!/bin/sh\n/usr/bin/printf '%s\\n' '{stderr}' >&2\nexit 1\n",
        encoding="utf-8",
    )
    source.chmod(0o500)
    execution_root = tmp_path / "execution-root"
    execution_root.mkdir(mode=0o700)
    binary, seal = native._seal_swift_analyzer_binary(source, execution_root)
    return binary, {"binary": seal["binary"], "execution_seal": seal}


def test_trusted_swift_analyzer_promotes_only_exact_domain_error(tmp_path: Path) -> None:
    reason = "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int"
    binary, receipt = _failing_receipt_bound_swift_analyzer(tmp_path, reason)

    try:
        with pytest.raises(RouteError) as captured:
            native._run_trusted_swift_analyzer(
                binary,
                receipt,
                [],
                allowed_domain_errors=native._SWIFT_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
            )
    finally:
        binary.parent.chmod(0o700)

    assert str(captured.value) == reason


@pytest.mark.parametrize(
    "stderr",
    [
        "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int32",
        "EMITTED_HELPER_SOURCE_MISMATCH:swift:non_zero_double:elmosNonZero",
        "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int\nextra-output",
        ("NATIVE_ANALYZER_FAILED:/tmp/forged/ElmosSwiftAnalyzer:SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int"),
    ],
)
def test_trusted_swift_analyzer_does_not_promote_unknown_multiline_or_forged_output(
    tmp_path: Path,
    stderr: str,
) -> None:
    binary, receipt = _failing_receipt_bound_swift_analyzer(tmp_path, stderr)

    try:
        with pytest.raises(RouteError) as captured:
            native._run_trusted_swift_analyzer(
                binary,
                receipt,
                [],
                allowed_domain_errors=native._SWIFT_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
            )
    finally:
        binary.parent.chmod(0o700)

    assert str(captured.value) == f"NATIVE_ANALYZER_FAILED:{binary}:{stderr}"


def _synthetic_java_toolchain(*, profile: tuple[str, ...] = ("test-profile",)) -> ExactToolchain:
    return ExactToolchain(
        language="java",
        version="21.0.11",
        executable="/fixed/java",
        auxiliary="/fixed/javac",
        profile=profile,
        executable_sha256="a" * 64,
        auxiliary_sha256="b" * 64,
    )


def _trusted_java_test_input(tmp_path: Path) -> tuple[Path, list[str]]:
    source = tmp_path / "Narrow.java"
    source.write_text(
        "public final class Narrow { public static int value(int input) { return input; } }\n",
        encoding="utf-8",
    )
    helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
    return helper, [str(source.resolve()), "value"]


@pytest.mark.parametrize(
    "reason",
    [
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int",
        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",
    ],
)
def test_trusted_java_analyzer_promotes_only_exact_domain_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    def fail(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        snapshot = Path(command[3])
        assert command == [toolchain.executable, "--source", "21", str(snapshot), *arguments]
        assert snapshot != helper
        assert snapshot.name == "Analyzer.java"
        assert snapshot.parent == cwd
        assert snapshot.read_bytes() == helper.read_bytes()
        assert snapshot.stat().st_mode & 0o777 == 0o600
        assert cwd.stat().st_mode & 0o777 == 0o700
        assert timeout == 120
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{reason}")

    monkeypatch.setattr(native, "_run", fail)
    with pytest.raises(RouteError) as captured:
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )

    assert str(captured.value) == reason


@pytest.mark.parametrize(
    "stderr",
    [
        "prefix:JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int",
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int:suffix",
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:long",
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int",
        "JAVA_FLOAT_PRECISION_OUTSIDE_CERTIFIED_SUBSET:float",
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int\nextra-output",
        "prefix:JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",
        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET:suffix",
        "JAVA_STRING_VALUE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",
        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET\nextra-output",
        (
            'Exception in thread "main" java.lang.IllegalArgumentException: '
            "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int\n"
            "\tat Analyzer.type(Analyzer.java:454)"
        ),
        (
            'Exception in thread "main" java.lang.IllegalArgumentException: '
            "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET\n"
            "\tat Analyzer.expression(Analyzer.java:571)"
        ),
        (
            'Exception in thread "main" java.lang.IllegalArgumentException: '
            "JAVA_UNSUPPORTED_TYPE:Object\n"
            "\tat Analyzer.type(Analyzer.java:474)"
        ),
        ("NATIVE_ANALYZER_FAILED:/tmp/forged/java:JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"),
        ("NATIVE_ANALYZER_FAILED:/tmp/forged/java:JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET"),
    ],
)
def test_trusted_java_analyzer_does_not_promote_stack_multiline_forged_or_near_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stderr: str,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    def fail(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        raise RouteError(f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{stderr}")

    monkeypatch.setattr(native, "_run", fail)
    with pytest.raises(RouteError) as captured:
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )

    assert str(captured.value) == f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{stderr}"


@pytest.mark.parametrize(
    "reason",
    [
        "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int",
        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET",
    ],
)
def test_trusted_java_analyzer_does_not_promote_forged_outer_executable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    forged = f"NATIVE_ANALYZER_FAILED:/forged/java:{reason}"
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)
    monkeypatch.setattr(
        native,
        "_run",
        lambda command, *, cwd, timeout=120: (_ for _ in ()).throw(RouteError(forged)),
    )

    with pytest.raises(RouteError) as captured:
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )

    assert str(captured.value) == forged


@pytest.mark.parametrize(
    "policy",
    [
        frozenset({"JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"}),
        native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS | frozenset({"JAVA_UNSUPPORTED_TYPE:Object"}),
    ],
)
def test_trusted_java_analyzer_rejects_domain_error_policy_subset_or_superset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    policy: frozenset[str],
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(
        native,
        "_run",
        lambda command, *, cwd, timeout=120: pytest.fail("invalid policy reached Java execution"),
    )

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_DOMAIN_ERROR_POLICY_INVALID$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=policy,
        )


def test_trusted_java_analyzer_rejects_helper_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    symlink = tmp_path / "Analyzer.java"
    symlink.symlink_to(helper)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_SOURCE_UNSAFE$"):
        native._run_trusted_java_analyzer(
            toolchain,
            symlink,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


def test_trusted_java_analyzer_rejects_helper_drift_before_error_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reason = "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    expected = native._java_analyzer_source_binding(helper)
    changed = {**expected, "sha256": "sha256:" + "b" * 64}
    bindings = iter(
        [
            expected,
            changed,
        ]
    )
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)
    monkeypatch.setattr(native, "_java_analyzer_source_binding", lambda path: next(bindings))
    monkeypatch.setattr(
        native,
        "_run",
        lambda command, *, cwd, timeout=120: (_ for _ in ()).throw(
            RouteError(f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{reason}")
        ),
    )

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


def test_trusted_java_analyzer_uses_private_snapshot_and_checks_success_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    def succeed(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        snapshot = Path(command[3])
        assert command == [toolchain.executable, "--source", "21", str(snapshot), *arguments]
        assert snapshot != helper
        assert snapshot.parent == cwd
        assert snapshot.read_bytes() == helper.read_bytes()
        assert snapshot.stat().st_mode & 0o777 == 0o600
        assert cwd.stat().st_mode & 0o777 == 0o700
        assert timeout == 120
        return {"result": "ok"}

    monkeypatch.setattr(native, "_run", succeed)
    assert native._run_trusted_java_analyzer(
        toolchain,
        helper,
        arguments,
        allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
    ) == {"result": "ok"}


def test_trusted_java_analyzer_rejects_snapshot_drift_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)

    def tamper_snapshot(command: list[str], *, cwd: Path, timeout: int = 120) -> dict[str, Any]:
        Path(command[3]).write_text("final class Forged {}\n", encoding="utf-8")
        return {"result": "forged"}

    monkeypatch.setattr(native, "_run", tamper_snapshot)
    with pytest.raises(RouteError, match="^JAVA_ANALYZER_SNAPSHOT_CHANGED_DURING_EXECUTION$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


def test_trusted_java_analyzer_rejects_original_helper_drift_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper, arguments = _trusted_java_test_input(tmp_path)
    expected = native._java_analyzer_source_binding(helper)
    changed = {**expected, "bytes": int(expected["bytes"]) + 1}
    bindings = iter([expected, changed])
    monkeypatch.setattr(native, "exact_toolchain", lambda language: toolchain)
    monkeypatch.setattr(native, "_java_analyzer_source_binding", lambda path: next(bindings))
    monkeypatch.setattr(native, "_run", lambda command, *, cwd, timeout=120: {"result": "ok"})

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_SOURCE_CHANGED_DURING_EXECUTION$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


def test_trusted_java_analyzer_rejects_toolchain_drift_after_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolchain = _synthetic_java_toolchain()
    changed = _synthetic_java_toolchain(profile=("changed-profile",))
    observed = iter([toolchain, changed])
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: next(observed))
    monkeypatch.setattr(native, "_run", lambda command, *, cwd, timeout=120: {"result": "ok"})

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_TOOLCHAIN_CHANGED$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


def test_trusted_java_analyzer_rejects_toolchain_drift_before_error_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reason = "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"
    toolchain = _synthetic_java_toolchain()
    changed = _synthetic_java_toolchain(profile=("changed-profile",))
    observed = iter([toolchain, changed])
    helper, arguments = _trusted_java_test_input(tmp_path)
    monkeypatch.setattr(native, "exact_toolchain", lambda language: next(observed))
    monkeypatch.setattr(
        native,
        "_run",
        lambda command, *, cwd, timeout=120: (_ for _ in ()).throw(
            RouteError(f"NATIVE_ANALYZER_FAILED:{toolchain.executable}:{reason}")
        ),
    )

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_TOOLCHAIN_CHANGED$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


@pytest.mark.parametrize(
    ("source_kind", "tail"),
    [
        ("relative", ["value"]),
        ("absolute", []),
        ("absolute", ["--inventory"]),
        ("absolute", ["value", "--unexpected"]),
        ("absolute", ["value\nforged"]),
    ],
)
def test_trusted_java_analyzer_rejects_non_analyze_command_shapes(
    tmp_path: Path,
    source_kind: str,
    tail: list[str],
) -> None:
    toolchain = _synthetic_java_toolchain()
    helper = ENGINE_ROOT / "native" / "java" / "Analyzer.java"
    source = "relative.java" if source_kind == "relative" else str(tmp_path / "Missing.java")
    arguments = [source, *tail]

    with pytest.raises(RouteError, match="^JAVA_ANALYZER_COMMAND_SHAPE_INVALID$"):
        native._run_trusted_java_analyzer(
            toolchain,
            helper,
            arguments,
            allowed_domain_errors=native._JAVA_ANALYZE_PROMOTABLE_DOMAIN_ERRORS,
        )


def _require_native_toolchain(language: str) -> None:
    try:
        exact_toolchain(language)  # type: ignore[arg-type]
    except RouteError as error:
        pytest.skip(str(error))


_TYPED_SOURCES = {
    "cpp": (
        ".cpp",
        "#include <string>\n"
        "std::string echo(std::string value) { return value; }\n"
        "double echoNumber(double value) { return value; }\n",
    ),
    "objc": (
        ".m",
        "#import <Foundation/Foundation.h>\n"
        "NSString *echo(NSString *value) { return value; }\n"
        "double echoNumber(double value) { return value; }\n",
    ),
    "swift": (
        ".swift",
        "func echo(_ value: String) -> String { return value }\n"
        "func echoNumber(_ value: Double) -> Double { return value }\n",
    ),
    "java": (
        ".java",
        "public final class Typed {\n"
        "  public static String echo(String value) { return value; }\n"
        "  public static double echoNumber(double value) { return value; }\n"
        "}\n",
    ),
}


def test_java_module_inventory_ignores_javac_synthetic_default_constructor(
    tmp_path: Path,
) -> None:
    _require_native_toolchain("java")
    source = tmp_path / "Add.java"
    source.write_text(
        "public final class Add {\n  public static long add(long left, long right) { return left + right; }\n}\n",
        encoding="utf-8",
    )

    inventory = inventory_module(source, "java")

    assert inventory["enumeration_status"] == "PASSED"
    assert inventory["diagnostics"] == []
    assert [subject["qualified_name"] for subject in inventory["subjects"]] == [
        "Add",
        "Add.add",
    ]
    assert [subject["declaration_kind"] for subject in inventory["subjects"]] == [
        "top-level-class-wrapper",
        "method",
    ]
    assert inventory["subjects"][0]["analyzable"] is False
    assert inventory["subjects"][1]["analyzable"] is True
    assert all(subject["declaration_kind"] != "constructor" for subject in inventory["subjects"])


def test_clang_inventory_and_analysis_ignore_ambient_header_and_sdk_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_native_toolchain("cpp")
    hostile_headers = tmp_path / "hostile-headers"
    hostile_headers.mkdir()
    (hostile_headers / "cstdint").write_text(
        '#error "ELMOS_HOSTILE_CPATH_EXECUTED"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("CPATH", str(hostile_headers))
    monkeypatch.setenv("CPLUS_INCLUDE_PATH", str(hostile_headers))
    monkeypatch.setenv("SDKROOT", str(tmp_path / "hostile-sdk"))
    monkeypatch.setenv("DEVELOPER_DIR", str(tmp_path / "hostile-xcode"))
    source = ENGINE_ROOT / "fixtures/module/cpp/equivalence_module.cpp"

    inventory = inventory_module(source, "cpp")
    semantic = analyze(source, "cpp", "calculate")

    assert inventory["enumeration_status"] == "PASSED"
    assert semantic.functions[0].name == "calculate"


def _emit_for_target(ir: SemanticIR, language: Language) -> tuple[EmittedFile, Function]:
    """Emit `ir` and return the file together with the function it actually defines.

    `emit()` runs the identifier plan, and several targets refuse the source
    spelling outright -- cpp and objc because their global symbol namespace is
    open, java and swift because of the runtime function namespace -- so the
    emitted symbol is routinely not the one that was analyzed.  A harness built
    from the *source* `Function` therefore calls a name the emitted file does
    not define, and the target compiler rejects it ("cannot find 'same' in
    scope") before a single observation is made.  Production already avoids
    this by holding on to the plan -- see `single_unit.emit_only` and the
    `target_function` passed at `engine.py:3359` -- so these tests do the same.
    Note this is the *target* function only; `validate_source` must still be
    given the source one, because the source file really does define it.
    """
    plan = plan_identifiers(ir, language)
    return emit(ir, language, identifier_plan=plan), target_ir_view(ir, plan).functions[0]


@pytest.mark.parametrize("language", ["cpp", "objc", "swift", "java"])
def test_native_source_and_target_execute_lossless_string_and_exact_fp64_observations(
    tmp_path: Path,
    language: str,
) -> None:
    _require_native_toolchain(language)
    suffix, content = _TYPED_SOURCES[language]
    source = tmp_path / ("Typed.java" if language == "java" else f"typed{suffix}")
    source.write_text(content, encoding="utf-8")

    string_ir = analyze(source, language, "echo")  # type: ignore[arg-type]
    string_function = string_ir.functions[0]
    string_value = '汉字\x00"\\\n🙂'
    string_cases = [
        {"args": [string_value], "expected": string_value},
        {"args": [""], "expected": ""},
    ]
    source_string = validate_source(
        source,
        language,  # type: ignore[arg-type]
        string_function,
        string_cases,
        tmp_path / "source-string",
    )
    emitted_string, emitted_string_function = _emit_for_target(string_ir, language)  # type: ignore[arg-type]
    target_string = validate(
        emitted_string,
        language,  # type: ignore[arg-type]
        emitted_string_function,
        string_cases,
        tmp_path / "target-string",
    )
    for report in (source_string, target_string):
        if language != "java":
            profile = report["toolchain"]["profile"]
            expected_profile = {
                "cpp": "c++20",
                "objc": "c17/objc-arc/Foundation/Apple-runtime",
                "swift": "swift-language-mode=6",
            }[language]
            assert expected_profile in profile
            assert "platform=Darwin/arm64" in profile
            assert "xcode=26.6/17F113" in profile
            assert "macosx-sdk=26.5" in profile
            assert report["toolchain"]["executable_sha256"]
        assert [item["encoding"] for item in report["observations"]] == [
            "hex-utf8",
            "hex-utf8",
        ]
        assert [item["value"] for item in report["observations"]] == [string_value, ""]

    number_ir = analyze(source, language, "echoNumber")  # type: ignore[arg-type]
    number_function = number_ir.functions[0]
    number_cases = [
        {"args": [-0.0], "expected": -0.0},
        {"args": [float("inf")], "expected": float("inf")},
        {"args": [float("-inf")], "expected": float("-inf")},
        {"args": [float("nan")], "expected": float("nan")},
        {"args": [0.1], "expected": 0.1},
    ]
    source_number = validate_source(
        source,
        language,  # type: ignore[arg-type]
        number_function,
        number_cases,
        tmp_path / "source-number",
    )
    emitted_number, emitted_number_function = _emit_for_target(number_ir, language)  # type: ignore[arg-type]
    target_number = validate(
        emitted_number,
        language,  # type: ignore[arg-type]
        emitted_number_function,
        number_cases,
        tmp_path / "target-number",
    )
    for report in (source_number, target_number):
        observations = report["observations"]
        assert all(item["encoding"] == "fp64-hex" for item in observations)
        assert observations[0]["raw"] == "8000000000000000"
        assert observations[1]["raw"] == "7ff0000000000000"
        assert observations[2]["raw"] == "fff0000000000000"
        assert math.isnan(observations[3]["value"])
        assert observations[4]["raw"] == "3fb999999999999a"


def _division_ir() -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Ratio.java",
            "analyzer": "test",
            "analyzer_version": "0",
            "functions": [
                {
                    "name": "ratio",
                    "parameters": [
                        {"name": "left", "type": "number"},
                        {"name": "right", "type": "number"},
                    ],
                    "return_type": "number",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "/",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )


def _string_equality_ir() -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Strings.java",
            "analyzer": "test",
            "analyzer_version": "0",
            "functions": [
                {
                    "name": "same",
                    "parameters": [
                        {"name": "left", "type": "string"},
                        {"name": "right", "type": "string"},
                    ],
                    "return_type": "boolean",
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "==",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    )


def test_swift_canonical_unicode_equality_diverges_from_java_code_unit_equality(
    tmp_path: Path,
) -> None:
    """Real runtimes prove why specialized Swift/Java string routes block.

    Swift String equality applies Unicode canonical equivalence, while Java
    String.equals compares its UTF-16 sequence.  U+00E9 and U+0065 U+0301 are
    therefore equal in Swift and unequal in Java even though both targets were
    emitted from the same canonical `==` expression.
    """

    _require_native_toolchain("swift")
    _require_native_toolchain("java")
    semantic = _string_equality_ir()
    arguments = ["\u00e9", "e\u0301"]
    swift_emitted, swift_function = _emit_for_target(semantic, "swift")
    swift_report = validate(
        swift_emitted,
        "swift",
        swift_function,
        [{"args": arguments, "expected": True}],
        tmp_path / "swift",
    )
    java_emitted, java_function = _emit_for_target(semantic, "java")
    java_report = validate(
        java_emitted,
        "java",
        java_function,
        [{"args": arguments, "expected": False}],
        tmp_path / "java",
    )
    assert swift_report["observations"][0]["value"] is True
    assert java_report["observations"][0]["value"] is False


@pytest.mark.parametrize(
    ("language", "helpers", "tamper_from", "tamper_to"),
    [
        ("cpp", _CPP_HELPERS, "value == 0.0", "value < 0.0"),
        ("objc", _OBJC_HELPERS, "value == 0.0", "value < 0.0"),
        ("swift", _SWIFT_HELPERS, "value == 0.0", "value < 0.0"),
    ],
)
def test_native_emitted_target_relifts_exact_helper_and_rejects_body_tamper(
    tmp_path: Path,
    language: str,
    helpers: dict[str, str],
    tamper_from: str,
    tamper_to: str,
) -> None:
    _require_native_toolchain(language)
    source_ir = _division_ir()
    emitted, target_function = _emit_for_target(source_ir, language)  # type: ignore[arg-type]
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")

    # Relifting reads the emitted file, so it must be asked for the symbol that
    # file defines, and compared against the target view rather than the source
    # IR -- the two differ by exactly the planned rename and nothing else.
    relifted = analyze(target, language, target_function.name, emitted_target=True)  # type: ignore[arg-type]
    assert relifted.functions[0].semantic_mapping() == target_function.semantic_mapping()
    _assert_required_spans(relifted.functions[0].to_mapping(), target)

    helper = helpers["non_zero_double"]
    assert helper in emitted.content
    tampered = emitted.content.replace(tamper_from, tamper_to, 1)
    assert tampered != emitted.content
    target.write_text(tampered, encoding="utf-8")
    with pytest.raises(RouteError, match="EMITTED_HELPER_SOURCE_MISMATCH") as captured:
        analyze(target, language, target_function.name, emitted_target=True)  # type: ignore[arg-type]
    if language == "swift":
        assert str(captured.value) == ("EMITTED_HELPER_SOURCE_MISMATCH:swift:non_zero_double:elmosNonZero")


def _assert_span(node: dict[str, Any], source: Path) -> None:
    span = node.get("source_span")
    assert isinstance(span, dict)
    assert span["file"] == source.name
    assert isinstance(span["start_byte"], int)
    assert isinstance(span["end_byte"], int)
    assert 0 <= span["start_byte"] < span["end_byte"] <= len(source.read_bytes())


def _assert_expression_spans(expression: dict[str, Any], source: Path) -> None:
    _assert_span(expression, source)
    if expression["kind"] == "binary":
        _assert_expression_spans(expression["left"], source)
        _assert_expression_spans(expression["right"], source)


def _assert_statement_spans(statement: dict[str, Any], source: Path) -> None:
    _assert_span(statement, source)
    if statement["kind"] == "return":
        _assert_expression_spans(statement["expression"], source)
    else:
        _assert_expression_spans(statement["condition"], source)
        for nested in statement["then"] + statement["else"]:
            _assert_statement_spans(nested, source)


def _assert_required_spans(function: dict[str, Any], source: Path) -> None:
    _assert_span(function, source)
    for parameter in function["parameters"]:
        _assert_span(parameter, source)
    for statement in function["body"]:
        _assert_statement_spans(statement, source)


@pytest.mark.parametrize(
    ("language", "relative_path"),
    [
        ("cpp", "fixtures/module/cpp/equivalence_module.cpp"),
        ("objc", "fixtures/module/objc/equivalence_module.m"),
        ("swift", "fixtures/module/swift/equivalence_module.swift"),
        ("java", "fixtures/module/java/EquivalenceModule.java"),
    ],
)
def test_native_analyzers_attach_utf8_byte_spans_to_every_required_node(
    language: str,
    relative_path: str,
) -> None:
    _require_native_toolchain(language)
    source = ENGINE_ROOT / relative_path
    semantic = analyze(source, language, "calculate")  # type: ignore[arg-type]
    _assert_required_spans(semantic.functions[0].to_mapping(), source)


@pytest.mark.parametrize(
    ("language", "suffix", "source", "reason"),
    [
        (
            "cpp",
            ".cpp",
            "long long value(long long input) { return input; }\n",
            "CPP_INTEGER_SPELLING_OUTSIDE_EXACT_PROFILE",
        ),
        (
            "cpp",
            ".cpp",
            "typedef int int64_t;\nint64_t value(int64_t input) { return input; }\n",
            "CPP_INTEGER_TYPEDEF_NOT_EXACT_INT64",
        ),
        (
            "objc",
            ".m",
            "#import <Foundation/Foundation.h>\nNSInteger value(NSInteger input) { return input; }\n",
            "OBJC_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
        ),
        (
            "objc",
            ".m",
            "typedef int int64_t;\nint64_t value(int64_t input) { return input; }\n",
            "OBJC_INTEGER_TYPEDEF_NOT_EXACT_INT64",
        ),
        (
            "swift",
            ".swift",
            "func value(_ input: Int) -> Int { return input }\n",
            "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
        ),
        (
            "java",
            ".java",
            "public final class Narrow { public static int value(int input) { return input; } }\n",
            "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET",
        ),
    ],
)
def test_platform_or_narrow_integer_spellings_fail_closed(
    tmp_path: Path,
    language: str,
    suffix: str,
    source: str,
    reason: str,
) -> None:
    _require_native_toolchain(language)
    path = tmp_path / ("Narrow.java" if language == "java" else "narrow" + suffix)
    path.write_text(source, encoding="utf-8")
    with pytest.raises(RouteError, match=reason) as captured:
        analyze(path, language, "value")  # type: ignore[arg-type]
    if language == "swift":
        assert str(captured.value) == "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int"
    if language == "java":
        assert str(captured.value) == "JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"


@pytest.mark.parametrize("operator", ["==", "!="])
def test_java_raw_string_reference_equality_fails_closed(tmp_path: Path, operator: str) -> None:
    _require_native_toolchain("java")
    source = tmp_path / "Strings.java"
    source.write_text(
        "public final class Strings {\n"
        f"  public static boolean same(String left, String right) {{ return left {operator} right; }}\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError) as captured:
        analyze(source, "java", "same")
    assert str(captured.value) == "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET"
    assert set(tmp_path.iterdir()) == {source}


@pytest.mark.parametrize(
    "harness",
    [_cpp_harness, _objc_harness, _swift_harness, _java_harness],
)
def test_expected_error_cases_remain_explicitly_not_run_until_case_isolation_exists(
    harness: Any,
) -> None:
    function = _division_ir().functions[0]
    cases = [{"args": [1.0, 0.0], "expected_error": "ELMOS_DIVIDE_BY_ZERO"}]
    with pytest.raises(RouteError, match="EXPECTED_ERROR_BEHAVIOR_NOT_RUN"):
        harness(function, cases)



def _stream_writing_script(tmp_path: Path, *, stdout: str, stderr: str, exit_code: int) -> Path:
    for text in (stdout, stderr):
        if "'" in text:
            raise AssertionError("test output must remain shell-literal safe")
    script = tmp_path / "noisy-build"
    body = ["#!/bin/sh"]
    if stdout:
        body.append(f"/usr/bin/printf '%s\\n' '{stdout}'")
    if stderr:
        body.append(f"/usr/bin/printf '%s\\n' '{stderr}' >&2")
    body.append(f"exit {exit_code}")
    script.write_text("\n".join(body) + "\n", encoding="utf-8")
    script.chmod(0o500)
    return script


def test_failed_target_validation_reports_stdout_even_when_stderr_is_noisy(tmp_path: Path) -> None:
    """A banner on stderr must not evict the real diagnostics on stdout.

    This is the exact shape of the ``dotnet build`` failure that previously
    surfaced only its first-run welcome text: the old wrapper selected
    ``stderr or stdout``, so a non-empty banner discarded the compiler error
    that explained the failure.
    """

    script = _stream_writing_script(
        tmp_path,
        stdout="error CS0101: the namespace already contains a definition for Migrated",
        stderr="Welcome to .NET! Telemetry is collected.",
        exit_code=1,
    )

    with pytest.raises(RouteError) as captured:
        _run([str(script)], tmp_path)

    message = str(captured.value)
    assert message.startswith("TARGET_VALIDATION_FAILED:noisy-build:returncode=1:")
    assert 'stdout="' in message
    assert 'stderr="' in message
    assert "CS0101" in message
    assert "Welcome to .NET!" in message


def test_failed_target_validation_redacts_secrets_and_host_paths(tmp_path: Path) -> None:
    """Both streams are disclosed, so both must be sanitised first.

    Surfacing stdout as well as stderr widens what a failure can leak into
    persisted evidence.  The diagnostic therefore carries the same redaction
    contract the assembly build wrapper applies.
    """

    completed = subprocess.CompletedProcess(
        args=["build"],
        returncode=23,
        stdout=f"compiler error at {tmp_path}/source.cs TOKEN=stdout-secret\nCS0101",
        stderr="Authorization: Bearer stderr-secret\nfirst-run warning",
    )

    stdout = _bounded_process_diagnostic(completed.stdout, cwd=tmp_path)
    stderr = _bounded_process_diagnostic(completed.stderr, cwd=tmp_path)

    # The actionable diagnostics survive.
    assert "CS0101" in stdout
    assert "first-run warning" in stderr
    # The secrets and host paths do not.
    assert "stdout-secret" not in stdout
    assert "stderr-secret" not in stderr
    assert str(tmp_path) not in stdout
    assert "<redacted>" in stdout
    assert "<redacted>" in stderr


def test_failed_target_validation_with_no_output_is_reported_explicitly(tmp_path: Path) -> None:
    """An empty diagnostic would read as "no reason recorded"; say so instead."""

    script = _stream_writing_script(tmp_path, stdout="", stderr="", exit_code=3)

    with pytest.raises(RouteError) as captured:
        _run([str(script)], tmp_path)

    assert str(captured.value) == (
        'TARGET_VALIDATION_FAILED:noisy-build:returncode=3:stdout="<empty>":stderr="<empty>"'
    )


def test_empty_host_signal_is_retried_once_but_not_promoted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A host-killed compiler gets one bounded retry, never a synthetic pass."""

    outcomes = iter(
        [
            subprocess.CompletedProcess(["compiler"], -15, stdout="", stderr=""),
            subprocess.CompletedProcess(["compiler"], 0, stdout="ok\n", stderr=""),
        ]
    )

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return next(outcomes)

    monkeypatch.setattr(validation.subprocess, "run", fake_run)
    completed = _run(["compiler"], tmp_path)

    assert completed.returncode == 0


def test_empty_host_signal_remains_failed_after_bounded_retry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    outcomes = iter(
        [
            subprocess.CompletedProcess(["compiler"], -15, stdout="", stderr=""),
            subprocess.CompletedProcess(["compiler"], -15, stdout="", stderr=""),
        ]
    )

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        del args, kwargs
        return next(outcomes)

    monkeypatch.setattr(validation.subprocess, "run", fake_run)
    with pytest.raises(RouteError, match=r"returncode=-15:stdout=\"<empty>\":stderr=\"<empty>\""):
        _run(["compiler"], tmp_path)


def test_failed_target_validation_bounds_each_stream_independently(tmp_path: Path) -> None:
    """One chatty stream must not truncate the other out of the report.

    Truncation keeps the tail, because a compiler prints its summary last.
    """

    stdout = "HEAD-MARKER" + ("s" * _PROCESS_DIAGNOSTIC_LIMIT) + "TAIL-STDOUT"
    stderr = "HEAD-MARKER" + ("e" * _PROCESS_DIAGNOSTIC_LIMIT) + "TAIL-STDERR"

    bounded_stdout = _bounded_process_diagnostic(stdout, cwd=tmp_path)
    bounded_stderr = _bounded_process_diagnostic(stderr, cwd=tmp_path)

    assert len(bounded_stdout) == _PROCESS_DIAGNOSTIC_LIMIT
    assert len(bounded_stderr) == _PROCESS_DIAGNOSTIC_LIMIT
    assert bounded_stdout.endswith("TAIL-STDOUT")
    assert bounded_stderr.endswith("TAIL-STDERR")
    assert "HEAD-MARKER" not in bounded_stdout
    assert "HEAD-MARKER" not in bounded_stderr


def _binary_function(parameter_type: str, return_type: str) -> Any:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "typescript",
            "source_file": "add.ts",
            "analyzer": "test",
            "analyzer_version": "1",
            "functions": [
                {
                    "name": "add",
                    "parameters": [
                        {"name": "left", "type": parameter_type},
                        {"name": "right", "type": parameter_type},
                    ],
                    "return_type": return_type,
                    "body": [
                        {
                            "kind": "return",
                            "expression": {
                                "kind": "binary",
                                "operator": "+",
                                "left": {"kind": "name", "value": "left"},
                                "right": {"kind": "name", "value": "right"},
                            },
                        }
                    ],
                }
            ],
            "diagnostics": [],
        }
    ).functions[0]


def test_python_harness_passes_float_literals_for_canonical_number_parameters() -> None:
    """Python annotations do not coerce, so the harness must supply the type.

    ``def add(left: float, right: float) -> float`` called as ``add(2, 3)``
    returns the integer ``5``.  The observation is then an int while the
    canonical value and every statically typed target carry float64 ``5.0``,
    and byte-exact evidence comparison rejects a route that is in fact correct.
    This is the defect that made every ``typescript→python`` workload fail.
    """

    harness = _python_harness(
        _binary_function("number", "number"),
        [{"args": [2, 3], "expected": 5}],
    )

    assert "migrated.add(2.0, 3.0)" in harness
    assert "migrated.add(2, 3)" not in harness
    assert "expected_0 = 5.0" in harness


def test_python_harness_keeps_integer_parameters_as_integers() -> None:
    """The float rendering must not leak into the integer canonical type."""

    harness = _python_harness(
        _binary_function("integer", "integer"),
        [{"args": [2, 3], "expected": 5}],
    )

    assert "migrated.add(2, 3)" in harness
    assert "2.0" not in harness


def test_python_harness_observation_round_trips_as_float64() -> None:
    """Execute the generated harness and confirm the recorded value is a float."""

    module = tmp = None
    import subprocess
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "migrated.py").write_text(
            "def add(left: float, right: float) -> float:\n    return (left + right)\n",
            encoding="utf-8",
        )
        (root / "route_harness.py").write_text(
            _python_harness(_binary_function("number", "number"), [{"args": [2, 3], "expected": 5}]),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [sys.executable, "route_harness.py"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.split("\t")[-1])
    # 5.0, not 5 -- this is exactly what the evidence comparison checks.
    assert payload["value"] == 5.0
    assert isinstance(payload["value"], float)
    del module, tmp


def test_python_harness_rejects_a_case_with_the_wrong_argument_count() -> None:
    """Parity with the Java and TypeScript harnesses, which already fail closed."""

    with pytest.raises(RouteError, match="PYTHON_CASE_ARGUMENT_COUNT_INVALID"):
        _python_harness(_binary_function("integer", "integer"), [{"args": [1], "expected": 1}])


def test_python_literal_fails_closed_on_type_mismatch() -> None:
    with pytest.raises(RouteError, match="PYTHON_CASE_NUMBER_REQUIRED"):
        _python_literal(True, "number")
    with pytest.raises(RouteError, match="PYTHON_CASE_INTEGER_OUTSIDE_INT64"):
        _python_literal(2**63, "integer")
    with pytest.raises(RouteError, match="PYTHON_CASE_BOOLEAN_REQUIRED"):
        _python_literal(1, "boolean")
    with pytest.raises(RouteError, match="PYTHON_CASE_TYPE_UNSUPPORTED:widget"):
        _python_literal(1, "widget")
