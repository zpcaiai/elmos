import shutil
from pathlib import Path

import pytest

from elmos_polyglot_route.clang_analyzer import analyze_clang
from elmos_polyglot_route.models import RouteError, SemanticIR

CLANGXX = shutil.which("clang++")
CLANG = shutil.which("clang")

requires_clang = pytest.mark.skipif(
    CLANGXX is None or CLANG is None,
    reason="Host clang/clang++ toolchain unavailable",
)


def _analyze(
    tmp_path: Path,
    suffix: str,
    language: str,
    source: str,
    function: str,
) -> SemanticIR:
    path = tmp_path / f"source{suffix}"
    path.write_text(source, encoding="utf-8")
    executable = CLANGXX if language == "cpp" else CLANG
    assert executable is not None
    return analyze_clang(path, language, function, executable, "test")


@requires_clang
def test_cpp_let_and_assign(tmp_path: Path) -> None:
    source = (
        "#include <cstdint>\n"
        "std::int64_t compute(std::int64_t n) {\n"
        "    std::int64_t total = 0;\n"
        "    total = total + n;\n"
        "    total += 5;\n"
        "    return total;\n"
        "}\n"
    )
    semantic = _analyze(tmp_path, ".cpp", "cpp", source, "compute")
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


@requires_clang
def test_cpp_while_with_break_and_continue(tmp_path: Path) -> None:
    source = (
        "#include <cstdint>\n"
        "std::int64_t loop_fn(std::int64_t n) {\n"
        "    std::int64_t i = 0;\n"
        "    std::int64_t sum = 0;\n"
        "    while (i < n) {\n"
        "        i += 1;\n"
        "        if (i == 3) {\n"
        "            continue;\n"
        "        }\n"
        "        if (i > 10) {\n"
        "            break;\n"
        "        }\n"
        "        sum += i;\n"
        "    }\n"
        "    return sum;\n"
        "}\n"
    )
    semantic = _analyze(tmp_path, ".cpp", "cpp", source, "loop_fn")
    fn = semantic.functions[0]
    assert len(fn.body) == 4
    while_stmt = fn.body[2]
    assert while_stmt.kind == "while"
    assert while_stmt.condition is not None and while_stmt.condition.kind == "binary"
    assert while_stmt.condition.operator == "<"

    while_body = while_stmt.body
    assert len(while_body) == 4
    assert while_body[0].kind == "assign"
    assert while_body[1].kind == "if"
    assert while_body[1].then_body[0].kind == "continue"
    assert while_body[2].kind == "if"
    assert while_body[2].then_body[0].kind == "break"
    assert while_body[3].kind == "assign"


@requires_clang
def test_cpp_for_monotonic_range(tmp_path: Path) -> None:
    source = (
        "#include <cstdint>\n"
        "std::int64_t for_fn(std::int64_t n) {\n"
        "    std::int64_t total = 0;\n"
        "    for (std::int64_t i = 0; i < n; ++i) {\n"
        "        total += i;\n"
        "    }\n"
        "    for (std::int64_t j = 0; j < 10; j += 2) {\n"
        "        total += j;\n"
        "    }\n"
        "    for (std::int64_t k = 0; k < 5; k = k + 1) {\n"
        "        total += k;\n"
        "    }\n"
        "    return total;\n"
        "}\n"
    )
    semantic = _analyze(tmp_path, ".cpp", "cpp", source, "for_fn")
    fn = semantic.functions[0]
    assert len(fn.body) == 5
    for1 = fn.body[1]
    assert for1.kind == "for"
    assert for1.name == "i"
    assert for1.declared_type == "integer"
    assert for1.step is None
    assert len(for1.body) == 1 and for1.body[0].kind == "assign"

    for2 = fn.body[2]
    assert for2.kind == "for"
    assert for2.name == "j"
    assert for2.step is not None and for2.step.value == 2

    for3 = fn.body[3]
    assert for3.kind == "for"
    assert for3.name == "k"
    assert for3.step is not None and for3.step.value == 1


@requires_clang
def test_cpp_user_call_and_member_access(tmp_path: Path) -> None:
    source = (
        "#include <cstdint>\n"
        "struct Point { std::int64_t x; std::int64_t y; };\n"
        "std::int64_t double_val(std::int64_t v) { return v * 2; }\n"
        "std::int64_t process(Point p) {\n"
        "    std::int64_t d = double_val(p.x);\n"
        "    return d + p.y;\n"
        "}\n"
    )
    semantic = _analyze(tmp_path, ".cpp", "cpp", source, "process")
    fn = semantic.functions[0]
    assert len(fn.body) == 2
    let_d = fn.body[0]
    assert let_d.kind == "let"
    assert let_d.name == "d"
    call_expr = let_d.expression
    assert call_expr is not None and call_expr.kind == "call"
    assert call_expr.function_name == "double_val"
    assert len(call_expr.call_arguments) == 1
    arg = call_expr.call_arguments[0]
    assert arg.kind == "member_access"
    assert arg.member == "x"
    assert arg.target is not None and arg.target.kind == "name" and arg.target.value == "p"


@requires_clang
def test_objc_let_assign_and_for(tmp_path: Path) -> None:
    source = (
        "typedef signed char BOOL;\n"
        "#define YES ((BOOL)1)\n"
        "#define NO ((BOOL)0)\n"
        "long long objc_compute(long long n) {\n"
        "    long long total = 0;\n"
        "    for (long long i = 0; i < n; ++i) {\n"
        "        total += i;\n"
        "    }\n"
        "    return total;\n"
        "}\n"
    )
    semantic = _analyze(tmp_path, ".m", "objc", source, "objc_compute")
    fn = semantic.functions[0]
    assert len(fn.body) == 3
    assert fn.body[0].kind == "let"
    assert fn.body[0].name == "total"
    assert fn.body[1].kind == "for"
    assert fn.body[1].name == "i"
    assert fn.body[2].kind == "return"


@requires_clang
def test_cpp_parameter_reassignment_fails_closed(tmp_path: Path) -> None:
    source = (
        "#include <cstdint>\n"
        "std::int64_t bad(std::int64_t n) {\n"
        "    n = n + 1;\n"
        "    return n;\n"
        "}\n"
    )
    with pytest.raises(RouteError, match="CPP_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:n"):
        _analyze(tmp_path, ".cpp", "cpp", source, "bad")


@requires_clang
def test_cpp_undeclared_assign_fails_closed(tmp_path: Path) -> None:
    source = (
        "#include <cstdint>\n"
        "std::int64_t global_var = 10;\n"
        "std::int64_t bad(std::int64_t n) {\n"
        "    global_var = n;\n"
        "    return global_var;\n"
        "}\n"
    )
    with pytest.raises(RouteError, match="CPP_ASSIGNMENT_TARGET_NOT_DECLARED:global_var"):
        _analyze(tmp_path, ".cpp", "cpp", source, "bad")
