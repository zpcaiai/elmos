"""Lifting while and for loops from PHP source code.

Verifies that PHP while loops (`while ($cond) { ... }`) and monotonic for loops
(`for ($i = 0; $i < $n; $i++) { ... }`) correctly lift into canonical IR loop statements,
reject non-monotonic, do-while, or non-block forms, and emit cleanly into target languages.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "subject.php"
    content = (
        "<?php\n\n"
        "declare(strict_types=1);\n\n"
        "function subject(int $n): int {\n"
        f"{body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_php_while_loop_lifts(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $x = $n;\n"
        "    while ($x > 0) {\n"
        "        $x--;\n"
        "        if ($x === 5) {\n"
        "            break;\n"
        "        }\n"
        "    }\n"
        "    return $x;",
    )
    semantic = analyze(source, "php", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[1].kind == "while"
    assert statements[1].condition is not None
    assert statements[1].condition.operator == ">"
    assert len(statements[1].body) == 2
    assert statements[1].body[0].kind == "assign"
    assert statements[1].body[1].kind == "if"
    assert statements[1].body[1].then_body[0].kind == "break"
    assert statements[2].kind == "return"


def test_php_for_loop_lifts_default_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $total = 0;\n"
        "    for ($i = 0; $i < $n; $i++) {\n"
        "        if ($i === 3) {\n"
        "            continue;\n"
        "        }\n"
        "        $total += $i;\n"
        "    }\n"
        "    return $total;",
    )
    semantic = analyze(source, "php", "subject")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    loop = statements[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.declared_type == "integer"
    assert loop.start is not None and loop.start.value == 0
    assert loop.end is not None and loop.end.value == "n"
    assert loop.step is None
    assert len(loop.body) == 2
    assert loop.body[0].kind == "if"
    assert loop.body[0].then_body[0].kind == "continue"
    assert loop.body[1].kind == "assign"


def test_php_for_loop_lifts_prefix_inc(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $total = 0;\n"
        "    for ($i = 0; $i < $n; ++$i) {\n"
        "        $total += $i;\n"
        "    }\n"
        "    return $total;",
    )
    semantic = analyze(source, "php", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.step is None


def test_php_for_loop_lifts_custom_step(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $total = 0;\n"
        "    for ($i = 0; $i < $n; $i += 2) {\n"
        "        $total += $i;\n"
        "    }\n"
        "    return $total;",
    )
    semantic = analyze(source, "php", "subject")
    loop = semantic.functions[0].body[1]
    assert loop.kind == "for"
    assert loop.name == "i"
    assert loop.step is not None and loop.step.value == 2


def test_php_do_while_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    do {\n"
        "        $n--;\n"
        "    } while ($n > 0);\n"
        "    return $n;",
    )
    with pytest.raises(RouteError, match="^PHP_DO_WHILE_REJECTED$"):
        analyze(source, "php", "subject")


def test_php_for_closed_range_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for ($i = 0; $i <= $n; $i++) {\n"
        "        break;\n"
        "    }\n"
        "    return $n;",
    )
    with pytest.raises(RouteError, match="^PHP_FOR_CLOSED_RANGE_REJECTED$"):
        analyze(source, "php", "subject")


def test_php_for_downto_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for ($i = $n; $i > 0; $i--) {\n"
        "        break;\n"
        "    }\n"
        "    return $n;",
    )
    with pytest.raises(RouteError, match="^PHP_FOR_DOWNTO_REJECTED$"):
        analyze(source, "php", "subject")


def test_php_for_loop_index_mutation_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    for ($i = 0; $i < $n; $i++) {\n"
        "        $i = 10;\n"
        "    }\n"
        "    return $n;",
    )
    with pytest.raises(RouteError, match="^PHP_CONSTANT_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:i$"):
        analyze(source, "php", "subject")


def test_php_break_outside_loop_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    break;\n"
        "    return $n;",
    )
    with pytest.raises(RouteError, match="^PHP_BREAK_OUTSIDE_LOOP$"):
        analyze(source, "php", "subject")


def test_php_continue_outside_loop_rejected(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    continue;\n"
        "    return $n;",
    )
    with pytest.raises(RouteError, match="^PHP_CONTINUE_OUTSIDE_LOOP$"):
        analyze(source, "php", "subject")


def test_php_loops_emit_across_targets_and_relift(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    $total = 0;\n"
        "    for ($i = 0; $i < $n; $i++) {\n"
        "        if ($i === 5) {\n"
        "            break;\n"
        "        }\n"
        "        $total += $i;\n"
        "    }\n"
        "    return $total;",
    )
    semantic = analyze(source, "php", "subject")

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

    # Target: PHP
    php_code = emit(semantic, "php").content
    assert "for ($i = 0; $i < $n; $i++) {" in php_code

    # Relift emitted PHP code
    target_file = tmp_path / "migrated.php"
    target_file.write_text(php_code, encoding="utf-8")
    relifted = analyze(target_file, "php", "subject", emitted_target=True)
    assert len(relifted.functions[0].body) == 3
    assert relifted.functions[0].body[1].kind == "for"
    assert relifted.functions[0].body[1].body[0].kind == "if"
    assert relifted.functions[0].body[1].body[0].then_body[0].kind == "break"
