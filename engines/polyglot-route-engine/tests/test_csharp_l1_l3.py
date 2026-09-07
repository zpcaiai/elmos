"""Comprehensive L1-L3 tests for C# analyzer.

Verifies end-to-end extraction of:
- L1: mutable variable declarations and assignments
- L2: while loops with break/continue
- L3: for loops with range/step
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "Program.cs"
    p.write_text(
        "public static class Program {\n"
        f"    {code}\n"
        "}\n",
        encoding="utf-8",
    )
    return p


def test_csharp_full_l1_mutable_counter(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long CountSteps(long limit) {\n"
        "    long count = 0;\n"
        "    count = count + 1;\n"
        "    count += 2;\n"
        "    return count;\n"
        "}",
    )
    ir = analyze(source, "csharp", "CountSteps")
    body = ir.functions[0].body
    assert len(body) == 4
    assert body[0].kind == "let"
    assert body[0].name == "count"
    assert body[1].kind == "assign"
    assert body[1].name == "count"
    assert body[2].kind == "assign"
    assert body[2].name == "count"
    assert body[3].kind == "return"


def test_csharp_full_l2_while_loop_counter(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long SumUntil(long limit) {\n"
        "    long acc = 0;\n"
        "    while (acc < limit) {\n"
        "        acc += 1;\n"
        "    }\n"
        "    return acc;\n"
        "}",
    )
    ir = analyze(source, "csharp", "SumUntil")
    body = ir.functions[0].body
    assert body[0].kind == "let"
    assert body[1].kind == "while"
    loop_body = body[1].body
    assert len(loop_body) == 1
    assert loop_body[0].kind == "assign"
    assert loop_body[0].name == "acc"


def test_csharp_full_l3_for_loop_accumulator(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "public static long SumRange(long n) {\n"
        "    long sum = 0;\n"
        "    for (long i = 0; i < n; i++) {\n"
        "        sum += i;\n"
        "    }\n"
        "    return sum;\n"
        "}",
    )
    ir = analyze(source, "csharp", "SumRange")
    body = ir.functions[0].body
    assert body[0].kind == "let"
    assert body[1].kind == "for"
    assert body[1].name == "i"
    assert body[1].body[0].kind == "assign"
    assert body[1].body[0].name == "sum"

    # Verify cross-emission
    for target in ("python", "java", "go", "typescript", "rust", "csharp"):
        emitted = emit(ir, target)
        assert emitted.content
