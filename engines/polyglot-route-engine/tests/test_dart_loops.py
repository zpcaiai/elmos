"""Lifting while and for loops from Dart / Flutter source code.

Verifies that Dart while loops (`while (cond) { ... }`) and monotonic for loops
(`for (int i = 0; i < n; i++) { ... }`) correctly lift into canonical IR loop statements,
reject non-monotonic, do-while, for-in, or non-int forms, and emit cleanly into target languages.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.source_analyzer import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.dart"
    content = (
        "int subject(int n) {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_dart_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  while (n > 0) {\n"
        "    break;\n"
        "  }\n"
        "  return n;",
    )
    semantic = analyze(source, "flutter", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "while"
    assert statements[0].condition is not None
    assert statements[0].condition.operator == ">"
    assert len(statements[0].body) == 1
    assert statements[0].body[0].kind == "break"
    assert statements[1].kind == "return"


def test_dart_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int total = 0;\n"
        "  for (int i = 0; i < n; i++) {\n"
        "    continue;\n"
        "  }\n"
        "  return total;",
    )
    semantic = analyze(source, "flutter", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    loop = statements[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.declared_type == "integer"
    assert loop.start is not None and loop.start.value == 0
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is None
    assert len(loop.body) == 1
    assert loop.body[0].kind == "continue"


def test_dart_for_loop_lifts_prefix_inc(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int total = 0;\n"
        "  for (int i = 0; i < n; ++i) {\n"
        "    total += i;\n"
        "  }\n"
        "  return total;",
    )
    semantic = analyze(source, "flutter", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.step is None
    assert len(loop.body) == 1
    assert loop.body[0].kind == "assign"


def test_dart_for_loop_lifts_custom_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int total = 0;\n"
        "  for (int i = 0; i < n; i += 2) {\n"
        "    total += i;\n"
        "  }\n"
        "  return total;",
    )
    semantic = analyze(source, "flutter", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.step is not None and loop.step.value == 2


def test_dart_do_while_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  do {\n"
        "    n--;\n"
        "  } while (n > 0);\n"
        "  return n;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET$",
    ):
        analyze(source, "flutter", "subject")


def test_dart_for_loop_non_integer_type_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  for (double i = 0.0; i < 10.0; i++) {\n"
        "    break;\n"
        "  }\n"
        "  return n;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_FOR_VARIABLE_TYPE_INVALID:number$",
    ):
        analyze(source, "flutter", "subject")


def test_dart_for_loop_non_monotonic_condition_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  for (int i = 0; i <= n; i++) {\n"
        "    break;\n"
        "  }\n"
        "  return n;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_FOR_CONDITION_NON_MONOTONIC$",
    ):
        analyze(source, "flutter", "subject")


def test_dart_for_loop_non_monotonic_updater_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  for (int i = 0; i < n; i--) {\n"
        "    break;\n"
        "  }\n"
        "  return n;",
    )
    with pytest.raises(
        RouteError,
        match="^DART_FOR_UPDATE_NON_MONOTONIC$",
    ):
        analyze(source, "flutter", "subject")


def test_dart_loops_emit_across_targets_and_relift(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "  int total = 0;\n"
        "  for (int i = 0; i < n; i++) {\n"
        "    if (i == 5) {\n"
        "      break;\n"
        "    }\n"
        "    total += i;\n"
        "  }\n"
        "  return total;",
    )
    semantic = analyze(source, "flutter", "subject")

    # Target: Python
    py_code = emit(semantic, "python").content
    assert "for i in range(0, n):" in py_code
    assert "break" in py_code

    # Target: TypeScript
    ts_code = emit(semantic, "typescript").content
    assert "for (let i: number = 0; i < n; i++)" in ts_code

    # Target: Go
    go_code = emit(semantic, "go").content
    assert "for i := int64(0); i < n; i++ {" in go_code

    # Target: Rust
    rs_code = emit(semantic, "rust").content
    assert "for i in 0..n {" in rs_code

    # Target: Flutter / Dart
    dart_code = emit(semantic, "flutter").content
    assert "for (int i = 0; i < n; i++) {" in dart_code

    # Relift emitted Dart code
    target_file = tmp_path / "migrated.dart"
    target_file.write_text(dart_code, encoding="utf-8")
    relifted = analyze(target_file, "flutter", "subject", emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[1].kind == "for"
    assert relifted.functions[0].body[1].body[0].kind == "if"
    assert relifted.functions[0].body[1].body[0].then_body[0].kind == "break"
