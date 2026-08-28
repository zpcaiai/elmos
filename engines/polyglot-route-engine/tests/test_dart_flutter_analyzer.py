from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from elmos_polyglot_route.dart_analyzer import (
    _HELPER,
    _package_closure,
    analyze_flutter,
    inventory_flutter,
)
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import Function, Parameter, RouteError
from elmos_polyglot_route.source_analyzer import analyze
from elmos_polyglot_route.toolchains import ExactToolchain, exact_toolchain
from elmos_polyglot_route.validation import _dart_harness

ENGINE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).parent / "fixtures" / "flutter"


def _run(
    command: list[str],
    cwd: Path,
    *,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_flutter_dispatch_uses_bundled_dart_ast_and_emits_concrete_spans() -> None:
    source = FIXTURES / "development" / "choose.dart"
    ir = analyze(source, "flutter", "choose")

    assert ir.source_language == "flutter"
    assert ir.analyzer == "Dart package:analyzer AST"
    assert ir.analyzer_version == "package:analyzer 10.1.0; Dart 3.12.1"
    assert ir.functions[0].name == "choose"
    assert ir.functions[0].body[0].kind == "let"
    assert ir.functions[0].body[1].kind == "if"
    assert ir.functions[0].source_span is not None
    assert ir.functions[0].source_span.end_byte == len(source.read_bytes()) - 1
    assert all(parameter.source_span is not None for parameter in ir.functions[0].parameters)


def test_flutter_inventory_is_ast_owned_and_marks_ui_non_analyzable() -> None:
    toolchain = exact_toolchain("flutter")
    pure = inventory_flutter(FIXTURES / "development" / "choose.dart", toolchain)
    widget = inventory_flutter(FIXTURES / "negative" / "widget.dart", toolchain)

    assert pure["kind"] == "elmos.typed-pure-module-inventory"
    assert [(item["name"], item["analyzable"]) for item in pure["subjects"]] == [("choose", True)]
    source_bytes = (FIXTURES / "development" / "choose.dart").read_bytes()
    assert pure["source_artifact_bytes"] == len(source_bytes)
    assert pure["source_artifact_sha256"] == (
        "sha256:" + hashlib.sha256(source_bytes).hexdigest()
    )
    ui_import = widget["subjects"][0]
    assert ui_import["declaration_kind"] == "flutter-ui-import"
    assert ui_import["analyzable"] is False


def test_flutter_expression_function_body_is_inventory_and_ir_analyzable(
    tmp_path: Path,
) -> None:
    source = tmp_path / "add.dart"
    source.write_text(
        "int add(int left, int right) => left + right;\n",
        encoding="utf-8",
    )
    toolchain = exact_toolchain("flutter")

    inventory = inventory_flutter(source, toolchain)
    subject = inventory["subjects"][0]
    assert subject["name"] == "add"
    assert subject["analyzable"] is True
    assert [parameter["name"] for parameter in subject["signature"]["parameters"]] == [
        "left",
        "right",
    ]

    function = analyze_flutter(source, "add", toolchain).functions[0]
    assert function.body[0].kind == "return"
    assert function.body[0].expression is not None
    assert function.body[0].expression.operator == "+"


@pytest.mark.parametrize(
    ("relative", "function_name", "diagnostic"),
    [
        ("negative/widget.dart", "build", "FLUTTER_UI_SEMANTICS_UNSUPPORTED"),
        ("negative/async.dart", "delayed", "DART_ASYNC_OR_GENERATOR_FUNCTION_UNSUPPORTED"),
        ("negative/effect.dart", "printAndReturn", "DART_UNSUPPORTED_STATEMENT"),
        ("negative/untyped.dart", "choose", "DART_EXPLICIT_PARAMETER_TYPE_REQUIRED"),
    ],
)
def test_flutter_analyzer_fails_closed_outside_typed_pure_module(
    relative: str,
    function_name: str,
    diagnostic: str,
) -> None:
    with pytest.raises(RouteError, match=f"^{diagnostic}"):
        analyze(FIXTURES / relative, "flutter", function_name)


def test_flutter_analyzer_refuses_path_dart_and_relifts_emitted_target(
    tmp_path: Path,
) -> None:
    flutter = exact_toolchain("flutter")
    path_dart = shutil.which("dart")
    assert path_dart is not None
    assert Path(path_dart).resolve() != Path(flutter.auxiliary or "").resolve()
    wrong = ExactToolchain(
        "flutter",
        flutter.version,
        flutter.executable,
        str(Path(path_dart).resolve()),
    )
    source = FIXTURES / "development" / "choose.dart"
    with pytest.raises(RouteError, match="^EXACT_TOOLCHAIN_FLUTTER_DART_PATH_MISMATCH$"):
        analyze_flutter(source, "choose", wrong)

    emitted = emit(analyze_flutter(source, "choose", flutter), "flutter")
    target = tmp_path / emitted.relative_path
    target.write_text(emitted.content, encoding="utf-8")
    target_ir = analyze_flutter(target, "choose", flutter, emitted_target=True)
    target_inventory = inventory_flutter(target, flutter, emitted_target=True)

    function = target_ir.functions[0]
    assert function.name == "choose"
    assert function.body[0].expression is not None
    assert function.body[0].expression.operator == "+"
    assert function.body[1].then_body[0].expression is not None
    assert function.body[1].then_body[0].expression.operator == "*"
    assert function.body[1].else_body[0].expression is not None
    assert function.body[1].else_body[0].expression.operator == "%"
    assert target_inventory["directives"] == []
    assert [subject["name"] for subject in target_inventory["subjects"]][-1] == "choose"


def test_dart_analyzer_kernel_compiler_and_runtime_are_real(tmp_path: Path) -> None:
    toolchain = exact_toolchain("flutter")
    dart = toolchain.auxiliary
    assert dart is not None
    flutter_root = Path(toolchain.executable).resolve().parent.parent
    restricted, _ = _package_closure(flutter_root)
    package_config = tmp_path / "package_config.json"
    package_config.write_text(json.dumps(restricted, sort_keys=True, separators=(",", ":")))
    kernel = tmp_path / "elmos-dart-analyzer.dill"
    compiled = _run(
        [
            dart,
            "compile",
            "kernel",
            f"--packages={package_config}",
            str(_HELPER),
            "-o",
            str(kernel),
        ],
        ENGINE_ROOT,
    )
    assert compiled.returncode == 0, compiled.stderr
    assert kernel.is_file() and kernel.stat().st_size > 0

    executed = _run(
        [dart, str(kernel), str(FIXTURES / "holdout" / "ratio.dart"), "ratio"],
        ENGINE_ROOT,
    )
    assert executed.returncode == 0, executed.stderr
    assert json.loads(executed.stdout)["functions"][0]["name"] == "ratio"


def test_bundled_dart_compiles_and_runs_a_pure_module_harness(tmp_path: Path) -> None:
    toolchain = exact_toolchain("flutter")
    dart = toolchain.auxiliary
    assert dart is not None
    shutil.copyfile(FIXTURES / "development" / "choose.dart", tmp_path / "choose.dart")
    (tmp_path / "main.dart").write_text(
        "import 'choose.dart';\n"
        "void main() {\n"
        "  final result = choose(1, 2, true);\n"
        "  if (result != 6) throw StateError('unexpected: $result');\n"
        "  print(result);\n"
        "}\n"
    )
    kernel = tmp_path / "pure-module.dill"
    analyzed = _run([dart, "analyze", "--fatal-infos", "--fatal-warnings", str(tmp_path)], tmp_path)
    assert analyzed.returncode == 0, analyzed.stderr
    compiled = _run([dart, "compile", "kernel", "main.dart", "-o", str(kernel)], tmp_path)
    assert compiled.returncode == 0, compiled.stderr
    executed = _run([dart, str(kernel)], tmp_path)
    assert executed.returncode == 0
    assert executed.stdout.strip() == "6"


@pytest.mark.parametrize(
    ("return_type", "value", "required", "absent"),
    [
        (
            "integer",
            1,
            (),
            ("dart:convert", "dart:typed_data", "_elmosHarnessFp64", "_elmosHarnessHexUtf8"),
        ),
        (
            "number",
            1.0,
            ("dart:typed_data", "_elmosHarnessFp64", "_elmosHarnessSameFp64"),
            ("dart:convert", "_elmosHarnessHexUtf8"),
        ),
        (
            "string",
            "value",
            ("dart:convert", "_elmosHarnessHexUtf8"),
            ("dart:typed_data", "_elmosHarnessFp64", "_elmosHarnessSameFp64"),
        ),
    ],
)
def test_dart_harness_emits_only_return_type_specific_helpers(
    return_type: str,
    value: object,
    required: tuple[str, ...],
    absent: tuple[str, ...],
) -> None:
    function = Function(
        name="identity",
        parameters=(Parameter(name="value", type=return_type),),
        return_type=return_type,
        body=(),
    )

    harness = _dart_harness(
        function,
        [{"args": [value], "expected": value}],
        f"{ {'integer': 'int', 'number': 'double', 'string': 'String'}[return_type] } "
        f"identity({ {'integer': 'int', 'number': 'double', 'string': 'String'}[return_type] } value) "
        "{ return value; }",
    )

    assert all(fragment in harness for fragment in required)
    assert all(fragment not in harness for fragment in absent)


def test_flutter_tool_compiles_and_runs_pure_module_test(tmp_path: Path) -> None:
    toolchain = exact_toolchain("flutter")
    flutter = toolchain.executable
    (tmp_path / "lib").mkdir()
    (tmp_path / "test").mkdir()
    shutil.copyfile(FIXTURES / "development" / "choose.dart", tmp_path / "lib" / "choose.dart")
    (tmp_path / "lib" / "main.dart").write_text(
        "import 'choose.dart';\n"
        "void main() {\n"
        "  if (choose(1, 2, true) != 6) throw StateError('runtime mismatch');\n"
        "}\n"
    )
    (tmp_path / "test" / "choose_test.dart").write_text(
        "import 'package:elmos_flutter_route_runtime/choose.dart';\n"
        "import 'package:flutter_test/flutter_test.dart';\n"
        "void main() {\n"
        "  test('pure Dart module executes in Flutter test runtime', () {\n"
        "    expect(choose(1, 2, true), 6);\n"
        "  });\n"
        "}\n"
    )
    (tmp_path / "pubspec.yaml").write_text(
        "name: elmos_flutter_route_runtime\n"
        "environment:\n"
        "  sdk: '>=3.12.1 <3.13.0'\n"
        "dependencies:\n"
        "  flutter:\n"
        "    sdk: flutter\n"
        "dev_dependencies:\n"
        "  flutter_test:\n"
        "    sdk: flutter\n"
    )
    environment = dict(os.environ)
    environment.update({"FLUTTER_SUPPRESS_ANALYTICS": "true", "DART_SUPPRESS_ANALYTICS": "true"})
    resolved = _run([flutter, "pub", "get", "--offline"], tmp_path, environment=environment)
    assert resolved.returncode == 0, resolved.stderr
    analyzed = _run([flutter, "analyze", "--no-pub"], tmp_path, environment=environment)
    assert analyzed.returncode == 0, analyzed.stderr
    tested = _run(
        [flutter, "test", "--no-pub", "test/choose_test.dart"],
        tmp_path,
        environment=environment,
    )
    assert tested.returncode == 0, tested.stderr
    built = _run([flutter, "build", "bundle", "--debug", "--no-pub"], tmp_path, environment=environment)
    assert built.returncode == 0, built.stderr
    assert (tmp_path / "build" / "flutter_assets" / "kernel_blob.bin").is_file()
