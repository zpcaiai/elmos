"""Lifting while and for loops from Swift source code.

Verifies that Swift while loops (`while cond { ... }`) and monotonic for loops
(`for i in 0..<n { ... }` or `for i in stride(from: 0, to: n, by: 2)`) correctly lift into canonical
IR loop statements, reject non-monotonic ranges, repeat-while, labels, loop variable mutations,
and emit cleanly across targets.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, target_ir_view
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze

SWIFTC = shutil.which("swiftc")
pytestmark = pytest.mark.skipif(SWIFTC is None, reason="swiftc is not installed")


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.swift"
    content = (
        "func subject(_ n: Int64) -> Int64 {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_swift_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var count: Int64 = n\n"
        "    while count > 0 {\n"
        "        break\n"
        "    }\n"
        "    return count",
    )
    semantic = analyze(source, "swift", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "while"
    assert statements[1].condition is not None
    assert statements[1].condition.operator == ">"
    assert len(statements[1].body) == 1
    assert statements[1].body[0].kind == "break"
    assert statements[2].kind == "return"


def test_swift_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in 0..<n {\n"
        "        continue\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "swift", "subject")
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


def test_swift_for_loop_lifts_stride(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in stride(from: 0, to: n, by: 2) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "swift", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.start is not None and loop.start.value == 0
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is not None and loop.step.value == 2
    assert len(loop.body) == 1
    assert loop.body[0].kind == "assign"


def test_swift_repeat_while_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var count: Int64 = n\n"
        "    repeat {\n"
        "        count -= 1\n"
        "    } while count > 0\n"
        "    return count",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET$",
    ):
        analyze(source, "swift", "subject")


def test_swift_labeled_loop_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    loop: while n > 0 {\n"
        "        break\n"
        "    }\n"
        "    return n",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET$",
    ):
        analyze(source, "swift", "subject")


def test_swift_for_closed_range_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in 0...n {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_FOR_CLOSED_RANGE_REJECTED$",
    ):
        analyze(source, "swift", "subject")


def test_swift_for_stride_through_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in stride(from: 0, through: n, by: 1) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_FOR_CLOSED_RANGE_REJECTED$",
    ):
        analyze(source, "swift", "subject")


def test_swift_for_down_to_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in stride(from: n, to: 0, by: -1) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_FOR_DOWNTO_REJECTED$",
    ):
        analyze(source, "swift", "subject")


def test_swift_for_non_positive_step_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in stride(from: 0, to: n, by: 0) {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_FOR_NON_POSITIVE_STEP_REJECTED$",
    ):
        analyze(source, "swift", "subject")


def test_swift_for_condition_non_monotonic_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in 10..<5 {\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_FOR_CONDITION_NON_MONOTONIC$",
    ):
        analyze(source, "swift", "subject")


def test_swift_for_loop_index_mutation_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in 0..<n {\n"
        "        i = 10\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:i$",
    ):
        analyze(source, "swift", "subject")


def test_swift_break_outside_loop_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    break\n"
        "    return n",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_BREAK_OUTSIDE_LOOP$",
    ):
        analyze(source, "swift", "subject")


def test_swift_continue_outside_loop_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    continue\n"
        "    return n",
    )
    with pytest.raises(
        RouteError,
        match="^SWIFT_CONTINUE_OUTSIDE_LOOP$",
    ):
        analyze(source, "swift", "subject")


def test_swift_loops_emit_across_targets_and_relift(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total: Int64 = 0\n"
        "    for i in 0..<n {\n"
        "        if i == 5 {\n"
        "            break\n"
        "        }\n"
        "        total += i\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "swift", "subject")

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

    # Target: Swift
    swift_code = emit(semantic, "swift").content
    assert "for i in Int64(0)..<n {" in swift_code

    # Relift emitted Swift code
    plan = plan_identifiers(semantic, "swift")
    symbol = target_ir_view(semantic, plan).functions[0].name
    target_file = tmp_path / "migrated.swift"
    target_file.write_text(swift_code, encoding="utf-8")
    relifted = analyze(target_file, "swift", symbol, emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[1].kind == "for"
    assert relifted.functions[0].body[1].body[0].kind == "if"
    assert relifted.functions[0].body[1].body[0].then_body[0].kind == "break"
