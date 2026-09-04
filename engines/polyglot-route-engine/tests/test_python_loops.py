"""Lifting while and for loops from Python source code.

Verifies that Python while and monotonic range-for loops correctly lift
into canonical IR loop statements, reject non-standard or unsupported forms,
and emit cleanly into target languages.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.python_analyzer import analyze_python


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.py"
    path.write_text(f"def subject(n: int) -> int:\n{body}\n", encoding="utf-8")
    return path


def test_python_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    i: int = 0\n"
        "    while i < n:\n"
        "        if i == 5:\n"
        "            break\n"
        "        i = i + 1\n"
        "    return i\n",
    )
    # Note: `i = i + 1` is unannotated assignment, which will be rejected.
    # In single-assignment certified subset, local variables in loop body are `let`.
    # Let's test single-assignment loop body:
    source = _source(
        tmp_path,
        "    while n > 0:\n"
        "        break\n"
        "    return n\n",
    )
    semantic = analyze_python(source, "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "while"
    assert statements[0].condition is not None
    assert statements[0].condition.operator == ">"
    assert len(statements[0].body) == 1
    assert statements[0].body[0].kind == "break"
    assert statements[1].kind == "return"


def test_python_for_range_lifts_one_arg(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    total: int = 0\n"
        "    for i in range(n):\n"
        "        continue\n"
        "    return total\n",
    )
    semantic = analyze_python(source, "subject")
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


def test_python_for_range_lifts_two_args(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    total: int = 0\n"
        "    for i in range(1, n):\n"
        "        continue\n"
        "    return total\n",
    )
    semantic = analyze_python(source, "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.start is not None and loop.start.value == 1
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is None


def test_python_for_range_lifts_three_args(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    total: int = 0\n"
        "    for i in range(1, n, 2):\n"
        "        continue\n"
        "    return total\n",
    )
    semantic = analyze_python(source, "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.start is not None and loop.start.value == 1
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is not None and loop.step.value == 2


def test_python_rejects_while_orelse(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    while n > 0:\n"
        "        break\n"
        "    else:\n"
        "        return 0\n"
        "    return n\n",
    )
    with pytest.raises(RouteError, match="PYTHON_WHILE_ORELSE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze_python(source, "subject")


def test_python_rejects_for_orelse(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for i in range(n):\n"
        "        continue\n"
        "    else:\n"
        "        return 0\n"
        "    return n\n",
    )
    with pytest.raises(RouteError, match="PYTHON_FOR_ORELSE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze_python(source, "subject")


def test_python_rejects_non_range_for(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for i in [1, 2, 3]:\n"
        "        continue\n"
        "    return n\n",
    )
    with pytest.raises(RouteError, match="PYTHON_NON_RANGE_FOR_OUTSIDE_CERTIFIED_SUBSET"):
        analyze_python(source, "subject")


def test_python_loop_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    total: int = 0\n"
        "    for i in range(0, n, 2):\n"
        "        while i > 10:\n"
        "            break\n"
        "        continue\n"
        "    return total\n",
    )
    semantic = analyze_python(source, "subject")
    for target in ("java", "go", "typescript", "rust", "csharp", "python"):
        content = emit(semantic, target).content
        assert "for" in content or "while" in content
        assert "break" in content
        assert "continue" in content
