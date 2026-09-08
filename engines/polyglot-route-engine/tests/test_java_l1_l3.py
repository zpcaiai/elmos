from pathlib import Path

import pytest

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, class_body: str) -> Path:
    path = tmp_path / "Subject.java"
    content = (
        "public final class Subject {\n"
        f"{class_body}\n"
        "}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_java_let_and_assign(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    public static long compute(long n) {\n"
        "        long total = 0;\n"
        "        total = total + n;\n"
        "        total += 5;\n"
        "        return total;\n"
        "    }\n",
    )
    semantic = analyze(source, "java", "compute")
    fn = semantic.functions[0]
    body = fn.body
    assert len(body) == 4
    assert body[0].kind == "let"
    assert body[0].name == "total"
    assert body[0].declared_type == "integer"
    assert body[0].expression is not None and body[0].expression.kind == "literal"
    assert body[0].expression.value == 0

    assert body[1].kind == "assign"
    assert body[1].name == "total"
    assert body[1].expression is not None and body[1].expression.kind == "binary"
    assert body[1].expression.operator == "+"

    assert body[2].kind == "assign"
    assert body[2].name == "total"
    assert body[2].expression is not None and body[2].expression.kind == "binary"
    assert body[2].expression.operator == "+"
    assert body[2].expression.left is not None and body[2].expression.left.kind == "name"
    assert body[2].expression.left.value == "total"
    assert body[2].expression.right is not None and body[2].expression.right.kind == "literal"
    assert body[2].expression.right.value == 5

    assert body[3].kind == "return"


def test_java_euclid_gcd_while(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    public static long gcd(long a, long b) {\n"
        "        long x = a;\n"
        "        long y = b;\n"
        "        while (y != 0) {\n"
        "            long temp = y;\n"
        "            y = x % y;\n"
        "            x = temp;\n"
        "        }\n"
        "        return x;\n"
        "    }\n",
    )
    semantic = analyze(source, "java", "gcd")
    fn = semantic.functions[0]
    assert len(fn.body) == 4
    assert fn.body[0].kind == "let" and fn.body[0].name == "x"
    assert fn.body[1].kind == "let" and fn.body[1].name == "y"
    while_stmt = fn.body[2]
    assert while_stmt.kind == "while"
    assert while_stmt.condition.operator == "!="
    assert len(while_stmt.body) == 3
    assert while_stmt.body[0].kind == "let" and while_stmt.body[0].name == "temp"
    assert while_stmt.body[1].kind == "assign" and while_stmt.body[1].name == "y"
    assert while_stmt.body[2].kind == "assign" and while_stmt.body[2].name == "x"
    assert fn.body[3].kind == "return"


def test_java_while_with_break_and_continue(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    public static long loop_fn(long n) {\n"
        "        long i = 0;\n"
        "        long sum = 0;\n"
        "        while (i < n) {\n"
        "            i += 1;\n"
        "            if (i == 3) {\n"
        "                continue;\n"
        "            }\n"
        "            if (i > 10) {\n"
        "                break;\n"
        "            }\n"
        "            sum += i;\n"
        "        }\n"
        "        return sum;\n"
        "    }\n",
    )
    semantic = analyze(source, "java", "loop_fn")
    fn = semantic.functions[0]
    assert len(fn.body) == 4
    while_stmt = fn.body[2]
    assert while_stmt.kind == "while"
    assert while_stmt.condition is not None and while_stmt.condition.kind == "binary"
    assert while_stmt.condition.operator == "<"

    while_body = while_stmt.body
    assert len(while_body) == 4
    assert while_body[0].kind == "assign" and while_body[0].name == "i"
    assert while_body[1].kind == "if"
    assert while_body[1].then_body[0].kind == "continue"
    assert while_body[2].kind == "if"
    assert while_body[2].then_body[0].kind == "break"
    assert while_body[3].kind == "assign" and while_body[3].name == "sum"


def test_java_rejects_parameter_reassignment(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    public static long bad_param(long n) {\n"
        "        n = n + 1;\n"
        "        return n;\n"
        "    }\n",
    )
    with pytest.raises(RouteError, match="JAVA_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:n"):
        analyze(source, "java", "bad_param")


def test_java_rejects_compound_parameter_reassignment(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "    public static long bad_param(long n) {\n"
        "        n += 1;\n"
        "        return n;\n"
        "    }\n",
    )
    with pytest.raises(RouteError, match="JAVA_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:n"):
        analyze(source, "java", "bad_param")
