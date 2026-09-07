"""Lifting while and for loops from TypeScript source code.

Verifies that TypeScript while loops (`while (cond) { ... }`) and monotonic for loops
(`for (let i: number = 0; i < n; i++) { ... }`) correctly lift into canonical IR loop statements,
reject non-monotonic, do-while, for-of, for-in, or non-let forms, and emit cleanly into target languages.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.ts"
    content = (
        "export function subject(n: number): number {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_typescript_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    while (n > 0) {\n"
        "        break;\n"
        "    }\n"
        "    return n;",
    )
    semantic = analyze(source, "typescript", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "while"
    assert statements[0].condition is not None
    assert statements[0].condition.operator == ">"
    assert len(statements[0].body) == 1
    assert statements[0].body[0].kind == "break"
    assert statements[1].kind == "return"


def test_typescript_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const total: number = 0;\n"
        "    for (let i: number = 0; i < n; i++) {\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    semantic = analyze(source, "typescript", "subject")
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


def test_typescript_for_loop_lifts_prefix_inc(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const total: number = 0;\n"
        "    for (let i: number = 0; i < n; ++i) {\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    semantic = analyze(source, "typescript", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.step is None


def test_typescript_for_loop_lifts_custom_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const total: number = 0;\n"
        "    for (let i: number = 1; i < n; i += 2) {\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    semantic = analyze(source, "typescript", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.start is not None and loop.start.value == 1
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is not None and loop.step.value == 2


def test_typescript_rejects_do_while(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    do {\n"
        "        break;\n"
        "    } while (n > 0);\n"
        "    return n;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "typescript", "subject")


def test_typescript_rejects_for_of(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for (const item of [1, 2, 3]) {\n"
        "        break;\n"
        "    }\n"
        "    return n;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_FOR_OF_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "typescript", "subject")


def test_typescript_rejects_for_in(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for (const key in n) {\n"
        "        break;\n"
        "    }\n"
        "    return n;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_FOR_IN_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "typescript", "subject")


def test_typescript_rejects_labeled_break(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    outer: while (n > 0) {\n"
        "        break outer;\n"
        "    }\n"
        "    return n;",
    )
    with pytest.raises(
        RouteError,
        match=(
            "TYPESCRIPT_LABELED_BREAK_OUTSIDE_CERTIFIED_SUBSET|"
            "TYPESCRIPT_UNSUPPORTED_STATEMENT:LabeledStatement"
        ),
    ):
        analyze(source, "typescript", "subject")


def test_typescript_rejects_non_monotonic_cond(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const total: number = 0;\n"
        "    for (let i: number = 0; i != n; i++) {\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_FOR_CONDITION_NON_MONOTONIC"):
        analyze(source, "typescript", "subject")


def test_typescript_rejects_non_monotonic_update(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const total: number = 0;\n"
        "    for (let i: number = 0; i < n; i--) {\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_FOR_UPDATE_NON_MONOTONIC"):
        analyze(source, "typescript", "subject")


def test_typescript_rejects_var_loop_variable(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    const total: number = 0;\n"
        "    for (var i: number = 0; i < n; i++) {\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    with pytest.raises(RouteError, match="TYPESCRIPT_FOR_VARIABLE_MUST_BE_LET"):
        analyze(source, "typescript", "subject")


def _source_integer(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.ts"
    content = (
        "type integer = number;\n"
        "export function subject(n: integer): integer {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_typescript_loop_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source_integer(
        tmp_path,
        "    const total: integer = 0;\n"
        "    for (let i: integer = 0; i < n; i += 2) {\n"
        "        while (i > 10) {\n"
        "            break;\n"
        "        }\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    semantic = analyze(source, "typescript", "subject")
    for target in ("java", "go", "typescript", "rust", "csharp", "python"):
        content = emit(semantic, target).content
        assert "for" in content or "while" in content
        assert "break" in content
        assert "continue" in content


def test_typescript_emitted_target_reanalysis(tmp_path: Path) -> None:
    source = _source_integer(
        tmp_path,
        "    const total: integer = 0;\n"
        "    for (let i: integer = 0; i < n; i += 1) {\n"
        "        while (i > 10) {\n"
        "            break;\n"
        "        }\n"
        "        continue;\n"
        "    }\n"
        "    return total;",
    )
    semantic = analyze(source, "typescript", "subject")
    emitted = emit(semantic, "typescript").content
    target_path = tmp_path / "emitted.ts"
    target_path.write_text(emitted, encoding="utf-8")
    reanalyzed = analyze(target_path, "typescript", "subject", emitted_target=True)
    assert len(reanalyzed.functions[0].body) == len(semantic.functions[0].body)
    assert reanalyzed.functions[0].body[1].kind == "for"
