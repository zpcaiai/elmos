"""Lifting while and for loops from Kotlin source code.

Verifies that Kotlin while loops (`while (cond) { ... }`) and monotonic for loops
(`for (i in 0L until n) { ... }`) correctly lift into canonical IR loop statements,
reject non-monotonic ranges, do-while, labels, loop variable mutations, and emit cleanly across targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.source_analyzer import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.kt"
    content = (
        "fun subject(n: Long): Long {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_kotlin_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var count: Long = n\n"
        "    while (count > 0L) {\n"
        "        break\n"
        "    }\n"
        "    return count",
    )
    semantic = analyze(source, "kotlin", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "while"
    assert statements[1].condition is not None
    assert statements[1].condition.operator == ">"
    assert len(statements[1].body) == 1
    assert statements[1].body[0].kind == "break"
    assert statements[2].kind == "return"


def test_kotlin_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Long = 0L\n"
        "    for (i in 0L until n) {\n"
        "        continue\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "kotlin", "subject")
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


def test_kotlin_for_loop_lifts_custom_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Long = 0L\n"
        "    for (i in 0L until n step 2L) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "kotlin", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.start is not None and loop.start.value == 0
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is not None and loop.step.value == 2
    assert len(loop.body) == 1
    assert loop.body[0].kind == "assign"


def test_kotlin_do_while_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var count: Long = n\n"
        "    do {\n"
        "        count -= 1L\n"
        "    } while (count > 0L)\n"
        "    return count",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_labeled_loop_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    loop@ while (n > 0L) {\n"
        "        break@loop\n"
        "    }\n"
        "    return n",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_for_closed_range_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Long = 0L\n"
        "    for (i in 0L..n) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_for_down_to_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Long = 0L\n"
        "    for (i in n downTo 0L) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_FOR_CONDITION_NON_MONOTONIC$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_for_loop_index_mutation_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Long = 0L\n"
        "    for (i in 0L until n) {\n"
        "        i = 10L\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:i$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_while_non_block_body_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    while (n > 0L) break\n"
        "    return n",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_WHILE_BLOCK_BODY_REQUIRED$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_for_non_block_body_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for (i in 0L until n) continue\n"
        "    return n",
    )
    with pytest.raises(
        RouteError,
        match="^KOTLIN_FOR_BLOCK_BODY_REQUIRED$",
    ):
        analyze(source, "kotlin", "subject")


def test_kotlin_loops_emit_across_targets_and_relift(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Long = 0L\n"
        "    for (i in 0L until n) {\n"
        "        if (i == 5L) {\n"
        "            break\n"
        "        }\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "kotlin", "subject")

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

    # Target: Kotlin
    kt_code = emit(semantic, "kotlin").content
    assert "for (i in 0L until n)" in kt_code

    # Relift emitted Kotlin code
    target_file = tmp_path / "migrated.kt"
    target_file.write_text(kt_code, encoding="utf-8")
    relifted = analyze(target_file, "kotlin", "subject", emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[1].kind == "for"
    assert relifted.functions[0].body[1].body[0].kind == "if"
    assert relifted.functions[0].body[1].body[0].then_body[0].kind == "break"
