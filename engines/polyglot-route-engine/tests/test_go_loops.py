"""Lifting while and for loops from Go source code.

Verifies that Go while loops (`for cond { ... }`) and monotonic 3-clause for loops
(`for i := int64(0); i < n; i++ { ... }`) correctly lift into canonical IR loop statements,
reject non-monotonic or non-standard forms, and emit cleanly into target languages.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "main.go"
    content = f"package main\n\nfunc subject(n int64) int64 {{\n{body}\n}}\n"
    path.write_text(content, encoding="utf-8")
    return path


def test_go_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for n > 0 {\n"
        "        break\n"
        "    }\n"
        "    return n",
    )
    semantic = analyze(source, "go", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "while"
    assert statements[0].condition is not None
    assert statements[0].condition.operator == ">"
    assert len(statements[0].body) == 1
    assert statements[0].body[0].kind == "break"
    assert statements[1].kind == "return"


def test_go_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total int64 = 0\n"
        "    for i := int64(0); i < n; i++ {\n"
        "        continue\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "go", "subject")
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


def test_go_for_loop_lifts_custom_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total int64 = 0\n"
        "    for i := int64(1); i < n; i += 2 {\n"
        "        continue\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "go", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.start is not None and loop.start.value == 1
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is not None and loop.step.value == 2


def test_go_rejects_infinite_loop(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for {\n"
        "        break\n"
        "    }\n"
        "    return n",
    )
    with pytest.raises(RouteError, match="GO_INFINITE_LOOP_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "go", "subject")


def test_go_rejects_non_monotonic_cond(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total int64 = 0\n"
        "    for i := int64(0); i != n; i++ {\n"
        "        continue\n"
        "    }\n"
        "    return total",
    )
    with pytest.raises(RouteError, match="GO_FOR_CONDITION_NON_MONOTONIC"):
        analyze(source, "go", "subject")


def test_go_loop_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    var total int64 = 0\n"
        "    for i := int64(0); i < n; i += 2 {\n"
        "        for i > 10 {\n"
        "            break\n"
        "        }\n"
        "        continue\n"
        "    }\n"
        "    return total",
    )
    semantic = analyze(source, "go", "subject")
    for target in ("java", "go", "typescript", "rust", "csharp", "python"):
        content = emit(semantic, target).content
        assert "for" in content or "while" in content
        assert "break" in content
        assert "continue" in content
