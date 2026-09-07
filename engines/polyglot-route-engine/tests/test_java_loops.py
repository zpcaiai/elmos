"""Lifting while and for loops from Java source code.

Verifies that Java while loops (`while (cond) { ... }`) and monotonic for loops
(`for (long i = 0; i < n; i++) { ... }`) correctly lift into canonical IR loop statements,
reject non-monotonic, do-while, or non-standard forms, and emit cleanly into target languages.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "Subject.java"
    content = (
        "public final class Subject {\n"
        "    public static long subject(long n) {\n"
        f"{body}\n"
        "    }\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_java_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        while (n > 0) {\n"
        "            break;\n"
        "        }\n"
        "        return n;",
    )
    semantic = analyze(source, "java", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "while"
    assert statements[0].condition is not None
    assert statements[0].condition.operator == ">"
    assert len(statements[0].body) == 1
    assert statements[0].body[0].kind == "break"
    assert statements[1].kind == "return"


def test_java_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        final long total = 0;\n"
        "        for (long i = 0; i < n; i++) {\n"
        "            continue;\n"
        "        }\n"
        "        return total;",
    )
    semantic = analyze(source, "java", "subject")
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


def test_java_for_loop_lifts_custom_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        final long total = 0;\n"
        "        for (long i = 1; i < n; i += 2) {\n"
        "            continue;\n"
        "        }\n"
        "        return total;",
    )
    semantic = analyze(source, "java", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.start is not None and loop.start.value == 1
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is not None and loop.step.value == 2


def test_java_rejects_do_while(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        do {\n"
        "            break;\n"
        "        } while (n > 0);\n"
        "        return n;",
    )
    with pytest.raises(RouteError, match="JAVA_DO_WHILE_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(source, "java", "subject")


def test_java_rejects_non_monotonic_cond(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        final long total = 0;\n"
        "        for (long i = 0; i != n; i++) {\n"
        "            continue;\n"
        "        }\n"
        "        return total;",
    )
    with pytest.raises(RouteError, match="JAVA_FOR_CONDITION_NON_MONOTONIC"):
        analyze(source, "java", "subject")


def test_java_rejects_non_monotonic_update(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        final long total = 0;\n"
        "        for (long i = 0; i < n; i--) {\n"
        "            continue;\n"
        "        }\n"
        "        return total;",
    )
    with pytest.raises(RouteError, match="JAVA_FOR_UPDATE_NON_MONOTONIC"):
        analyze(source, "java", "subject")


def test_java_loop_emits_to_all_targets(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "        final long total = 0;\n"
        "        for (long i = 0; i < n; i += 2) {\n"
        "            while (i > 10) {\n"
        "                break;\n"
        "            }\n"
        "            continue;\n"
        "        }\n"
        "        return total;",
    )
    semantic = analyze(source, "java", "subject")
    for target in ("java", "go", "typescript", "rust", "csharp", "python"):
        content = emit(semantic, target).content
        assert "for" in content or "while" in content
        assert "break" in content
        assert "continue" in content
