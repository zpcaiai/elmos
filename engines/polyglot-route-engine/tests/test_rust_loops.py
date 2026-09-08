"""Lifting loops (while, for, break, continue) from Rust source code.

Verifies that Rust `while` and monotonic `for in start..end` loops lift into
canonical loop IR, `break` and `continue` lift cleanly, labeled loops and closed
ranges are rejected, and lifted loop structures emit across targets.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "lib.rs"
    content = f"{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def test_rust_while_loop_basic(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn count(n: i64) -> i64 {\n"
        "    let mut i: i64 = 0;\n"
        "    let mut sum: i64 = 0;\n"
        "    while i < n {\n"
        "        i += 1;\n"
        "        sum += i;\n"
        "    }\n"
        "    return sum;\n"
        "}",
    )
    semantic = analyze(source, "rust", "count")
    body = semantic.functions[0].body
    assert len(body) == 4
    while_stmt = body[2]
    assert while_stmt.kind == "while"
    assert while_stmt.condition is not None and while_stmt.condition.kind == "binary"
    assert while_stmt.condition.operator == "<"
    assert len(while_stmt.body) == 2
    assert while_stmt.body[0].kind == "assign"
    assert while_stmt.body[1].kind == "assign"


def test_rust_while_with_break_and_continue(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn loop_fn(n: i64) -> i64 {\n"
        "    let mut i: i64 = 0;\n"
        "    let mut sum: i64 = 0;\n"
        "    while i < n {\n"
        "        i += 1;\n"
        "        if i == 3 {\n"
        "            continue;\n"
        "        }\n"
        "        if i > 10 {\n"
        "            break;\n"
        "        }\n"
        "        sum += i;\n"
        "    }\n"
        "    return sum;\n"
        "}",
    )
    semantic = analyze(source, "rust", "loop_fn")
    body = semantic.functions[0].body
    while_stmt = body[2]
    assert while_stmt.kind == "while"
    loop_body = while_stmt.body
    assert len(loop_body) == 4
    assert loop_body[0].kind == "assign"
    assert loop_body[1].kind == "if"
    assert loop_body[1].then_body[0].kind == "continue"
    assert loop_body[2].kind == "if"
    assert loop_body[2].then_body[0].kind == "break"
    assert loop_body[3].kind == "assign"


def test_rust_for_loop_half_open_range(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn for_fn(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    for i in 0..n {\n"
        "        total += i;\n"
        "    }\n"
        "    return total;\n"
        "}",
    )
    semantic = analyze(source, "rust", "for_fn")
    body = semantic.functions[0].body
    assert len(body) == 3
    for_stmt = body[1]
    assert for_stmt.kind == "for"
    assert for_stmt.name == "i"
    assert for_stmt.declared_type == "integer"
    assert for_stmt.start is not None and for_stmt.start.value == 0
    assert for_stmt.end is not None and for_stmt.end.value == "n"
    assert for_stmt.step is None
    assert len(for_stmt.body) == 1
    assert for_stmt.body[0].kind == "assign"


def test_rust_for_loop_with_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn for_step(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    for j in (0..10).step_by(2) {\n"
        "        total += j;\n"
        "    }\n"
        "    for k in (0..n).step_by(3 as usize) {\n"
        "        total += k;\n"
        "    }\n"
        "    return total;\n"
        "}",
    )
    semantic = analyze(source, "rust", "for_step")
    body = semantic.functions[0].body
    assert len(body) == 4
    for1 = body[1]
    assert for1.kind == "for"
    assert for1.name == "j"
    assert for1.step is not None and for1.step.value == 2
    for2 = body[2]
    assert for2.kind == "for"
    assert for2.name == "k"
    assert for2.step is not None and for2.step.value == 3


def test_rust_for_closed_range_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn for_fn(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    for i in 0..=n {\n"
        "        total += i;\n"
        "    }\n"
        "    return total;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_FOR_RANGE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "rust", "for_fn")


def test_rust_labeled_while_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn labeled(n: i64) -> i64 {\n"
        "    let mut i: i64 = 0;\n"
        "    'my_loop: while i < n {\n"
        "        i += 1;\n"
        "    }\n"
        "    return i;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "rust", "labeled")


def test_rust_labeled_for_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn labeled(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    'my_for: for i in 0..n {\n"
        "        total += i;\n"
        "    }\n"
        "    return total;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_LABELED_LOOP_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "rust", "labeled")


def test_rust_loop_local_scope_does_not_leak(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn leak_test(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    while total < n {\n"
        "        let inner: i64 = 1;\n"
        "        total += inner;\n"
        "    }\n"
        "    inner = 2;\n"
        "    return total;\n"
        "}",
    )
    with pytest.raises(RouteError, match="RUST_ASSIGNMENT_TARGET_NOT_DECLARED:inner"):
        analyze(source, "rust", "leak_test")


def test_rust_loops_emit_across_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn sum_evens(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    for i in (0..n).step_by(2) {\n"
        "        total += i;\n"
        "    }\n"
        "    return total;\n"
        "}",
    )
    semantic = analyze(source, "rust", "sum_evens")
    assert "for (long i = 0; i < n; i += 2)" in emit(semantic, "csharp").content
    assert "for i in range(0, n, 2):" in emit(semantic, "python").content
    assert "for (let i: number = 0; i < n; i += 2)" in emit(semantic, "typescript").content
    assert "for i := int64(0); i < n; i += 2 {" in emit(semantic, "go").content
    assert "for (long i = 0; i < n; i += 2)" in emit(semantic, "java").content
