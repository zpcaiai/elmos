"""Cross-language function call semantic equivalence and verification test suite.

Verifies that:
1. Python, Go, Java, and TypeScript frontends lift semantically equivalent
   multi-function calls (direct pure function calls in same module) to identical
   canonical SemanticIR structures.
2. Topological sorting places callees before callers in all frontends.
3. Fail-closed cycle detection rejects direct and mutual recursion across all frontends.
4. Function call IR passes canonical typing invariants (types.check).
5. Multi-function modules emit to all 14 routed languages with callee before caller.
6. Python, TypeScript, and Go emitted targets execute to identical runtime values.
7. Multi-language round-trip lifting and alpha-normalization preserves equivalence.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import alpha_normalize_target, plan_identifiers, target_ir_view
from elmos_polyglot_route.models import ROUTED_LANGUAGES, RouteError, SemanticIR
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.toolchains import exact_toolchain


def _strip_spans(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_spans(v) for k, v in obj.items() if k != "source_span"}
    elif isinstance(obj, list):
        return [_strip_spans(elem) for elem in obj]
    return obj


def _normalize_ir_for_comparison(ir: SemanticIR) -> dict[str, Any]:
    mapping = ir.to_mapping()
    mapping.pop("analyzer", None)
    mapping.pop("analyzer_version", None)
    mapping.pop("source_file", None)
    mapping.pop("source_language", None)
    mapping.pop("diagnostics", None)
    return _strip_spans(mapping)


# ==============================================================================
# 1. Direct Function Call Parity (Helper + Entrypoint)
# ==============================================================================

def test_direct_function_call_cross_language_parity(tmp_path: Path) -> None:
    # Python
    py_file = tmp_path / "math_ops.py"
    py_file.write_text(
        "def double_val(x: int) -> int:\n"
        "    return x * 2\n\n"
        "def compute(a: int, b: int) -> int:\n"
        "    return double_val(a) + double_val(b)\n",
        encoding="utf-8",
    )

    # TypeScript
    ts_file = tmp_path / "math_ops.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function double_val(x: integer): integer {\n"
        "    return x * 2;\n"
        "}\n\n"
        "export function compute(a: integer, b: integer): integer {\n"
        "    return double_val(a) + double_val(b);\n"
        "}\n",
        encoding="utf-8",
    )

    # Go
    go_file = tmp_path / "math_ops.go"
    go_file.write_text(
        "package main\n\n"
        "func double_val(x int64) int64 {\n"
        "    return x * 2\n"
        "}\n\n"
        "func compute(a int64, b int64) int64 {\n"
        "    return double_val(a) + double_val(b)\n"
        "}\n",
        encoding="utf-8",
    )

    # Java
    java_file = tmp_path / "MathOps.java"
    java_file.write_text(
        "public final class MathOps {\n"
        "    public static long double_val(long x) {\n"
        "        return x * 2;\n"
        "    }\n\n"
        "    public static long compute(long a, long b) {\n"
        "        return double_val(a) + double_val(b);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    ir_py = analyze(py_file, "python", "compute")
    ir_ts = analyze(ts_file, "typescript", "compute")
    ir_go = analyze(go_file, "go", "compute")
    ir_java = analyze(java_file, "java", "compute")

    for ir in (ir_py, ir_ts, ir_go, ir_java):
        types.check(ir)
        assert len(ir.functions) == 2
        # Topological order: callee before caller
        assert [f.name for f in ir.functions] == ["double_val", "compute"]
        # Callee check
        callee = ir.functions[0]
        assert callee.name == "double_val"
        assert len(callee.parameters) == 1
        assert callee.return_type == "integer"
        # Caller check
        caller = ir.functions[1]
        assert caller.name == "compute"
        assert len(caller.parameters) == 2
        assert caller.return_type == "integer"
        assert caller.body[0].kind == "return"
        ret_expr = caller.body[0].expression
        assert ret_expr is not None
        assert ret_expr.kind == "binary"
        assert ret_expr.operator == "+"
        assert ret_expr.left.kind == "call"
        assert ret_expr.left.function_name == "double_val"
        assert ret_expr.right.kind == "call"
        assert ret_expr.right.function_name == "double_val"

    norm_py = _normalize_ir_for_comparison(ir_py)
    norm_ts = _normalize_ir_for_comparison(ir_ts)
    norm_go = _normalize_ir_for_comparison(ir_go)
    norm_java = _normalize_ir_for_comparison(ir_java)

    assert norm_py == norm_ts
    assert norm_ts == norm_go
    assert norm_go == norm_java


# ==============================================================================
# 2. Multi-Step Call Chain & Reverse Source Order Topological Sorting
# ==============================================================================

def test_multistep_call_chain_topological_sort(tmp_path: Path) -> None:
    # Defined in reverse dependency order in Go (top -> mid -> base)
    go_file = tmp_path / "chain.go"
    go_file.write_text(
        "package main\n\n"
        "func top_calc(x int64) int64 {\n"
        "    return mid_calc(x) - 5\n"
        "}\n\n"
        "func mid_calc(x int64) int64 {\n"
        "    return base_calc(x) * 2\n"
        "}\n\n"
        "func base_calc(x int64) int64 {\n"
        "    return x + 10\n"
        "}\n",
        encoding="utf-8",
    )

    # Defined in Python
    py_file = tmp_path / "chain.py"
    py_file.write_text(
        "def base_calc(x: int) -> int:\n"
        "    return x + 10\n\n"
        "def mid_calc(x: int) -> int:\n"
        "    return base_calc(x) * 2\n\n"
        "def top_calc(x: int) -> int:\n"
        "    return mid_calc(x) - 5\n",
        encoding="utf-8",
    )

    # Defined in Java (reverse order)
    java_file = tmp_path / "Chain.java"
    java_file.write_text(
        "public final class Chain {\n"
        "    public static long top_calc(long x) {\n"
        "        return mid_calc(x) - 5;\n"
        "    }\n\n"
        "    public static long mid_calc(long x) {\n"
        "        return base_calc(x) * 2;\n"
        "    }\n\n"
        "    public static long base_calc(long x) {\n"
        "        return x + 10;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    # Defined in TypeScript
    ts_file = tmp_path / "chain.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function top_calc(x: integer): integer {\n"
        "    return mid_calc(x) - 5;\n"
        "}\n\n"
        "export function mid_calc(x: integer): integer {\n"
        "    return base_calc(x) * 2;\n"
        "}\n\n"
        "export function base_calc(x: integer): integer {\n"
        "    return x + 10;\n"
        "}\n",
        encoding="utf-8",
    )

    ir_go = analyze(go_file, "go", "top_calc")
    ir_py = analyze(py_file, "python", "top_calc")
    ir_java = analyze(java_file, "java", "top_calc")
    ir_ts = analyze(ts_file, "typescript", "top_calc")

    for ir in (ir_go, ir_py, ir_java, ir_ts):
        types.check(ir)
        assert len(ir.functions) == 3
        # Strict topological order: base -> mid -> top
        assert [f.name for f in ir.functions] == ["base_calc", "mid_calc", "top_calc"]

    assert _normalize_ir_for_comparison(ir_go) == _normalize_ir_for_comparison(ir_py)
    assert _normalize_ir_for_comparison(ir_py) == _normalize_ir_for_comparison(ir_java)
    assert _normalize_ir_for_comparison(ir_java) == _normalize_ir_for_comparison(ir_ts)


# ==============================================================================
# 3. Fail-Closed Recursion Rejection Across All Analyzers
# ==============================================================================

def test_direct_recursion_rejection(tmp_path: Path) -> None:
    # Python
    py_file = tmp_path / "rec.py"
    py_file.write_text(
        "def self_rec(n: int) -> int:\n"
        "    return self_rec(n - 1)\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(py_file, "python", "self_rec")

    # TypeScript
    ts_file = tmp_path / "rec.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function self_rec(n: integer): integer {\n"
        "    return self_rec(n - 1);\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(ts_file, "typescript", "self_rec")

    # Go
    go_file = tmp_path / "rec.go"
    go_file.write_text(
        "package main\n\n"
        "func self_rec(n int64) int64 {\n"
        "    return self_rec(n - 1)\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(go_file, "go", "self_rec")

    # Java
    java_file = tmp_path / "Rec.java"
    java_file.write_text(
        "public final class Rec {\n"
        "    public static long self_rec(long n) {\n"
        "        return self_rec(n - 1);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(java_file, "java", "self_rec")


def test_mutual_recursion_rejection(tmp_path: Path) -> None:
    # Python
    py_file = tmp_path / "mutual.py"
    py_file.write_text(
        "def fn_a(n: int) -> int:\n"
        "    return fn_b(n - 1)\n\n"
        "def fn_b(n: int) -> int:\n"
        "    return fn_a(n - 1)\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(py_file, "python", "fn_a")

    # TypeScript
    ts_file = tmp_path / "mutual.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function fn_a(n: integer): integer {\n"
        "    return fn_b(n - 1);\n"
        "}\n\n"
        "export function fn_b(n: integer): integer {\n"
        "    return fn_a(n - 1);\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(ts_file, "typescript", "fn_a")

    # Go
    go_file = tmp_path / "mutual.go"
    go_file.write_text(
        "package main\n\n"
        "func fn_a(n int64) int64 {\n"
        "    return fn_b(n - 1)\n"
        "}\n\n"
        "func fn_b(n int64) int64 {\n"
        "    return fn_a(n - 1)\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(go_file, "go", "fn_a")

    # Java
    java_file = tmp_path / "Mutual.java"
    java_file.write_text(
        "public final class Mutual {\n"
        "    public static long fn_a(long n) {\n"
        "        return fn_b(n - 1);\n"
        "    }\n\n"
        "    public static long fn_b(long n) {\n"
        "        return fn_a(n - 1);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        analyze(java_file, "java", "fn_a")


# ==============================================================================
# 4. Multi-Target Emission Across All 14 Routed Languages
# ==============================================================================

@pytest.mark.parametrize("target", ROUTED_LANGUAGES)
def test_multicall_emits_to_all_14_targets(tmp_path: Path, target: str) -> None:
    py_file = tmp_path / "ops.py"
    py_file.write_text(
        "def helper(x: int) -> int:\n"
        "    return x + 1\n\n"
        "def main_op(x: int) -> int:\n"
        "    return helper(x) * 2\n",
        encoding="utf-8",
    )
    ir = analyze(py_file, "python", "main_op")
    emitted = emit(ir, target)
    assert emitted.content
    assert emitted.relative_path

    # Check topological ordering: callee identifier appears before caller identifier
    plan = plan_identifiers(ir, target)
    fn_map = {b.source_name: b.target_name for b in plan.bindings if b.role == "function"}
    helper_target = fn_map["helper"]
    main_target = fn_map["main_op"]

    assert helper_target in emitted.content
    assert main_target in emitted.content
    assert emitted.content.index(helper_target) < emitted.content.rindex(main_target)


# ==============================================================================
# 5. Differential Runtime Execution (Python vs TypeScript vs Go)
# ==============================================================================

def test_multicall_differential_runtime_execution(tmp_path: Path) -> None:
    py_file = tmp_path / "math_ops.py"
    py_file.write_text(
        "def step_one(x: int) -> int:\n"
        "    return x * 3 + 2\n\n"
        "def step_two(x: int, y: int) -> int:\n"
        "    return step_one(x) + step_one(y)\n",
        encoding="utf-8",
    )
    ir = analyze(py_file, "python", "step_two")

    emitted_py = emit(ir, "python").content
    emitted_ts = emit(ir, "typescript").content
    emitted_go = emit(ir, "go").content

    run_dir = tmp_path / "run"
    run_dir.mkdir()

    node_toolchain = exact_toolchain("typescript")
    go_toolchain = exact_toolchain("go")

    test_inputs = [(0, 0), (1, 2), (5, 10), (-2, 4), (100, 200)]

    for x_val, y_val in test_inputs:
        # 1. Run Python
        py_script = f"{emitted_py}\nprint(step_two({x_val}, {y_val}))\n"
        py_res = subprocess.run(
            ["python3", "-c", py_script],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # 2. Run TypeScript via node
        ts_runner = run_dir / f"test_{x_val}_{y_val}.ts"
        ts_runner.write_text(f"{emitted_ts}\nconsole.log(step_two({x_val}, {y_val}));\n", encoding="utf-8")
        ts_res = subprocess.run(
            [node_toolchain.executable, str(ts_runner)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # 3. Run Go
        go_source = run_dir / f"main_{x_val}_{y_val}.go"
        go_code = emitted_go.replace("package main\n", "package main\nimport \"fmt\"\n", 1)
        go_source.write_text(
            f"{go_code}\nfunc main() {{\n    fmt.Println(step_two({x_val}, {y_val}))\n}}\n",
            encoding="utf-8",
        )
        go_res = subprocess.run(
            [go_toolchain.executable, "run", str(go_source)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        assert py_res == ts_res == go_res, f"Divergence for ({x_val}, {y_val}): py={py_res}, ts={ts_res}, go={go_res}"


# ==============================================================================
# 6. Multi-Language Round-Trip Lifting & Reanalysis
# ==============================================================================

def test_multicall_roundtrip_reanalysis(tmp_path: Path) -> None:
    py_src = tmp_path / "source.py"
    py_src.write_text(
        "def inc(x: int) -> int:\n"
        "    return x + 1\n\n"
        "def compute(n: int) -> int:\n"
        "    return inc(n) * 2\n",
        encoding="utf-8",
    )
    ir_original = analyze(py_src, "python", "compute")
    assert len(ir_original.functions) == 2

    for lang, filename in [("go", "subject.go"), ("java", "Migrated.java"), ("typescript", "subject.ts")]:
        plan = plan_identifiers(ir_original, lang)
        em = emit(ir_original, lang, identifier_plan=plan)
        target_path = tmp_path / filename
        target_path.write_text(em.content, encoding="utf-8")

        # Analyze entrypoint ("compute" mapped target name)
        entrypoint_binding = [b for b in plan.bindings if b.source_name == "compute" and b.role == "function"][0]
        relifted = analyze(target_path, lang, entrypoint_binding.target_name, emitted_target=True)

        assert len(relifted.functions) == 2
        # Verify alpha normalization succeeds and recovers exact semantic IR
        normalized = alpha_normalize_target(ir_original, relifted, plan)
        assert [f.name for f in normalized.functions] == ["inc", "compute"]
        assert _normalize_ir_for_comparison(normalized) == _normalize_ir_for_comparison(ir_original)
