from pathlib import Path

from elmos_polyglot_route.native import analyze


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "lib.rs"
    content = f"{body}\n"
    path.write_text(content, encoding="utf-8")
    return path


def test_rust_let_and_assign(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn compute(n: i64) -> i64 {\n"
        "    let mut total: i64 = 0;\n"
        "    total = total + n;\n"
        "    total += 5;\n"
        "    return total;\n"
        "}",
    )
    semantic = analyze(source, "rust", "compute")
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


def test_rust_euclid_gcd_while(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn gcd(a: i64, b: i64) -> i64 {\n"
        "    let mut x: i64 = a;\n"
        "    let mut y: i64 = b;\n"
        "    while y != 0 {\n"
        "        let temp: i64 = y;\n"
        "        y = x % y;\n"
        "        x = temp;\n"
        "    }\n"
        "    return x;\n"
        "}",
    )
    semantic = analyze(source, "rust", "gcd")
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


def test_rust_tail_expression_implicit_return(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "pub fn square(x: i64) -> i64 {\n"
        "    let result: i64 = x * x;\n"
        "    result\n"
        "}",
    )
    semantic = analyze(source, "rust", "square")
    fn = semantic.functions[0]
    assert len(fn.body) == 2
    assert fn.body[0].kind == "let" and fn.body[0].name == "result"
    assert fn.body[1].kind == "return"
    assert fn.body[1].expression is not None and fn.body[1].expression.kind == "name"
    assert fn.body[1].expression.value == "result"
