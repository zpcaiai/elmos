"""Cross-language loop semantic equivalence and verification test suite.

Verifies that:
1. Python, Go, Java, and TypeScript frontends lift semantically equivalent
   loop constructs (monotonic for loops, custom-step for loops, while loops,
   break, continue) to identical canonical SemanticIR structures.
2. The loop SemanticIR successfully passes canonical typing invariants (`types.check`).
3. Loop constructs cleanly emit to all 14 routed target languages.
4. Python, TypeScript, and Go emitted targets execute to identical runtime values.
5. Multi-language round-trip lifting and reanalysis preserves semantic equivalence.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers, target_ir_view
from elmos_polyglot_route.models import ROUTED_LANGUAGES, Parameter, SemanticIR
from elmos_polyglot_route.native import analyze
from elmos_polyglot_route.toolchains import exact_toolchain


def _strip_spans(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_spans(v) for k, v in obj.items() if k != "source_span"}
    elif isinstance(obj, list):
        return [_strip_spans(elem) for elem in obj]
    return obj


def _normalize_ir_for_comparison(ir: SemanticIR) -> dict[str, Any]:
    """Strip implementation metadata (analyzer name, version, source file, spans) to compare pure semantic structure."""
    mapping = ir.to_mapping()
    mapping.pop("analyzer", None)
    mapping.pop("analyzer_version", None)
    mapping.pop("source_file", None)
    mapping.pop("source_language", None)
    mapping.pop("diagnostics", None)
    return _strip_spans(mapping)


# ==============================================================================
# 1. Monotonic For Loop Parity (Search loop with return)
# ==============================================================================

def test_monotonic_for_loop_cross_language_parity(tmp_path: Path) -> None:
    # Python
    py_file = tmp_path / "subject.py"
    py_file.write_text(
        "def subject(n: int) -> int:\n"
        "    for i in range(0, n):\n"
        "        if i == 5:\n"
        "            return i\n"
        "    return 0\n",
        encoding="utf-8",
    )

    # Go
    go_file = tmp_path / "subject.go"
    go_file.write_text(
        "package main\n\n"
        "func subject(n int64) int64 {\n"
        "    for i := int64(0); i < n; i++ {\n"
        "        if i == 5 {\n"
        "            return i\n"
        "        }\n"
        "    }\n"
        "    return 0\n"
        "}\n",
        encoding="utf-8",
    )

    # Java
    java_file = tmp_path / "Subject.java"
    java_file.write_text(
        "public final class Subject {\n"
        "    public static long subject(long n) {\n"
        "        for (long i = 0; i < n; i++) {\n"
        "            if (i == 5) {\n"
        "                return i;\n"
        "            }\n"
        "        }\n"
        "        return 0;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    # TypeScript
    ts_file = tmp_path / "subject.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function subject(n: integer): integer {\n"
        "    for (let i: integer = 0; i < n; i++) {\n"
        "        if (i === 5) {\n"
        "            return i;\n"
        "        }\n"
        "    }\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    ir_py = analyze(py_file, "python", "subject")
    ir_go = analyze(go_file, "go", "subject")
    ir_java = analyze(java_file, "java", "subject")
    ir_ts = analyze(ts_file, "typescript", "subject")

    # Verify type invariants
    for ir in (ir_py, ir_go, ir_java, ir_ts):
        types.check(ir)

    norm_py = _normalize_ir_for_comparison(ir_py)
    norm_go = _normalize_ir_for_comparison(ir_go)
    norm_java = _normalize_ir_for_comparison(ir_java)
    norm_ts = _normalize_ir_for_comparison(ir_ts)

    assert norm_py == norm_go
    assert norm_go == norm_java
    assert norm_java == norm_ts

    # Detailed structural assertions
    fn = ir_py.functions[0]
    assert fn.parameters == (Parameter(name="n", type="integer"),)
    assert fn.return_type == "integer"
    assert len(fn.body) == 2
    assert fn.body[0].kind == "for"
    assert fn.body[0].name == "i"
    assert fn.body[0].declared_type == "integer"
    assert fn.body[0].start.value == 0
    assert fn.body[0].end.value == "n"
    assert fn.body[0].step is None
    assert fn.body[0].body[0].kind == "if"
    assert fn.body[1].kind == "return"


# ==============================================================================
# 2. Monotonic For Loop with Custom Step Parity (Local binding + continue/return)
# ==============================================================================

def test_for_loop_custom_step_cross_language_parity(tmp_path: Path) -> None:
    py_file = tmp_path / "subject.py"
    py_file.write_text(
        "def subject(n: int) -> int:\n"
        "    for i in range(1, n, 2):\n"
        "        val: int = i + 1\n"
        "        if val == 6:\n"
        "            continue\n"
        "        if val > 8:\n"
        "            return val\n"
        "    return 0\n",
        encoding="utf-8",
    )

    go_file = tmp_path / "subject.go"
    go_file.write_text(
        "package main\n\n"
        "func subject(n int64) int64 {\n"
        "    for i := int64(1); i < n; i += 2 {\n"
        "        var val int64 = i + 1\n"
        "        if val == 6 {\n"
        "            continue\n"
        "        }\n"
        "        if val > 8 {\n"
        "            return val\n"
        "        }\n"
        "    }\n"
        "    return 0\n"
        "}\n",
        encoding="utf-8",
    )

    java_file = tmp_path / "Subject.java"
    java_file.write_text(
        "public final class Subject {\n"
        "    public static long subject(long n) {\n"
        "        for (long i = 1; i < n; i += 2) {\n"
        "            final long val = i + 1;\n"
        "            if (val == 6) {\n"
        "                continue;\n"
        "            }\n"
        "            if (val > 8) {\n"
        "                return val;\n"
        "            }\n"
        "        }\n"
        "        return 0;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    ts_file = tmp_path / "subject.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function subject(n: integer): integer {\n"
        "    for (let i: integer = 1; i < n; i += 2) {\n"
        "        const val: integer = i + 1;\n"
        "        if (val === 6) {\n"
        "            continue;\n"
        "        }\n"
        "        if (val > 8) {\n"
        "            return val;\n"
        "        }\n"
        "    }\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    ir_py = analyze(py_file, "python", "subject")
    ir_go = analyze(go_file, "go", "subject")
    ir_java = analyze(java_file, "java", "subject")
    ir_ts = analyze(ts_file, "typescript", "subject")

    for ir in (ir_py, ir_go, ir_java, ir_ts):
        types.check(ir)

    norm_py = _normalize_ir_for_comparison(ir_py)
    norm_go = _normalize_ir_for_comparison(ir_go)
    norm_java = _normalize_ir_for_comparison(ir_java)
    norm_ts = _normalize_ir_for_comparison(ir_ts)

    assert norm_py == norm_go
    assert norm_go == norm_java
    assert norm_java == norm_ts

    loop = ir_py.functions[0].body[0]
    assert loop.step is not None
    assert loop.step.value == 2
    assert loop.body[0].kind == "let"
    assert loop.body[0].name == "val"
    assert loop.body[1].then_body[0].kind == "continue"


# ==============================================================================
# 3. While Loop with Break Parity (Countdown with Threshold Stop)
# ==============================================================================

def test_while_loop_with_break_cross_language_parity(tmp_path: Path) -> None:
    py_file = tmp_path / "subject.py"
    py_file.write_text(
        "def subject(n: int) -> int:\n"
        "    while n > 0:\n"
        "        if n == 5:\n"
        "            break\n"
        "        return n\n"
        "    return 0\n",
        encoding="utf-8",
    )

    go_file = tmp_path / "subject.go"
    go_file.write_text(
        "package main\n\n"
        "func subject(n int64) int64 {\n"
        "    for n > 0 {\n"
        "        if n == 5 {\n"
        "            break\n"
        "        }\n"
        "        return n\n"
        "    }\n"
        "    return 0\n"
        "}\n",
        encoding="utf-8",
    )

    java_file = tmp_path / "Subject.java"
    java_file.write_text(
        "public final class Subject {\n"
        "    public static long subject(long n) {\n"
        "        while (n > 0) {\n"
        "            if (n == 5) {\n"
        "                break;\n"
        "            }\n"
        "            return n;\n"
        "        }\n"
        "        return 0;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    ts_file = tmp_path / "subject.ts"
    ts_file.write_text(
        "type integer = number;\n"
        "export function subject(n: integer): integer {\n"
        "    while (n > 0) {\n"
        "        if (n === 5) {\n"
        "            break;\n"
        "        }\n"
        "        return n;\n"
        "    }\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )

    ir_py = analyze(py_file, "python", "subject")
    ir_go = analyze(go_file, "go", "subject")
    ir_java = analyze(java_file, "java", "subject")
    ir_ts = analyze(ts_file, "typescript", "subject")

    for ir in (ir_py, ir_go, ir_java, ir_ts):
        types.check(ir)

    norm_py = _normalize_ir_for_comparison(ir_py)
    norm_go = _normalize_ir_for_comparison(ir_go)
    norm_java = _normalize_ir_for_comparison(ir_java)
    norm_ts = _normalize_ir_for_comparison(ir_ts)

    assert norm_py == norm_go
    assert norm_go == norm_java
    assert norm_java == norm_ts

    fn = ir_py.functions[0]
    assert fn.body[0].kind == "while"
    assert fn.body[0].condition.operator == ">"
    assert fn.body[0].body[0].kind == "if"
    assert fn.body[0].body[0].then_body[0].kind == "break"
    assert fn.body[0].body[1].kind == "return"


# ==============================================================================
# 4. Multi-Target Emission Across All 14 Routed Languages
# ==============================================================================

@pytest.mark.parametrize("target", ROUTED_LANGUAGES)
def test_for_loop_emits_to_all_14_targets(tmp_path: Path, target: str) -> None:
    py_file = tmp_path / "subject.py"
    py_file.write_text(
        "def subject(n: int) -> int:\n"
        "    for i in range(0, n, 3):\n"
        "        if i == 6:\n"
        "            continue\n"
        "        if i > 10:\n"
        "            return i\n"
        "    return 0\n",
        encoding="utf-8",
    )
    ir = analyze(py_file, "python", "subject")
    emitted = emit(ir, target)
    assert emitted.content
    assert emitted.relative_path
    assert "for" in emitted.content or "while" in emitted.content
    assert "continue" in emitted.content


@pytest.mark.parametrize("target", ROUTED_LANGUAGES)
def test_while_loop_emits_to_all_14_targets(tmp_path: Path, target: str) -> None:
    py_file = tmp_path / "subject.py"
    py_file.write_text(
        "def subject(n: int) -> int:\n"
        "    while n > 0:\n"
        "        if n == 2:\n"
        "            break\n"
        "        return n\n"
        "    return 0\n",
        encoding="utf-8",
    )
    ir = analyze(py_file, "python", "subject")
    emitted = emit(ir, target)
    assert emitted.content
    assert emitted.relative_path
    assert "while" in emitted.content or "for" in emitted.content
    assert "break" in emitted.content


# ==============================================================================
# 5. Differential Runtime Execution (Python vs TypeScript vs Go)
# ==============================================================================

def test_loop_differential_runtime_execution(tmp_path: Path) -> None:
    """Execute emitted Python, TypeScript, and Go artifacts and verify identical output."""
    py_file = tmp_path / "subject.py"
    py_file.write_text(
        "def subject(n: int) -> int:\n"
        "    for i in range(1, n, 2):\n"
        "        val: int = i + 1\n"
        "        if val == 6:\n"
        "            continue\n"
        "        if val > 8:\n"
        "            return val\n"
        "    return 0\n",
        encoding="utf-8",
    )
    ir = analyze(py_file, "python", "subject")

    # Emit to Python, TypeScript, and Go
    emitted_py = emit(ir, "python").content
    emitted_ts = emit(ir, "typescript").content
    emitted_go = emit(ir, "go").content

    # Target files
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    node_toolchain = exact_toolchain("typescript")
    go_toolchain = exact_toolchain("go")

    test_inputs = [0, 1, 5, 8, 10, 15]

    for val in test_inputs:
        # 1. Run Python
        py_script = f"{emitted_py}\nprint(subject({val}))\n"
        py_res = subprocess.run(
            ["python3", "-c", py_script],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # 2. Run TypeScript via node
        ts_runner = run_dir / f"test_{val}.ts"
        ts_runner.write_text(f"{emitted_ts}\nconsole.log(subject({val}));\n", encoding="utf-8")
        ts_res = subprocess.run(
            [node_toolchain.executable, str(ts_runner)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        # 3. Run Go
        go_source = run_dir / f"main_{val}.go"
        go_code = emitted_go.replace("package main\n", "package main\nimport \"fmt\"\n", 1)
        go_source.write_text(
            f"{go_code}\nfunc main() {{\n    fmt.Println(subject({val}))\n}}\n",
            encoding="utf-8",
        )
        go_res = subprocess.run(
            [go_toolchain.executable, "run", str(go_source)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

        assert py_res == ts_res == go_res, f"Divergence for input {val}: py={py_res}, ts={ts_res}, go={go_res}"


# ==============================================================================
# 6. Multi-Language Round-Trip Lifting & Reanalysis
# ==============================================================================

def test_loop_roundtrip_reanalysis(tmp_path: Path) -> None:
    # Python source -> IR
    py_src = tmp_path / "source.py"
    py_src.write_text(
        "def subject(n: int) -> int:\n"
        "    for i in range(0, n):\n"
        "        if i == 5:\n"
        "            return i\n"
        "    return 0\n",
        encoding="utf-8",
    )
    ir_original = analyze(py_src, "python", "subject")

    # For each target, plan identifiers, emit, and relift via analyze(..., emitted_target=True)
    for lang, filename in [("go", "subject.go"), ("java", "Migrated.java"), ("typescript", "subject.ts")]:
        plan = plan_identifiers(ir_original, lang)
        em = emit(ir_original, lang, identifier_plan=plan)
        target_fn = target_ir_view(ir_original, plan).functions[0]
        target_path = tmp_path / filename
        target_path.write_text(em.content, encoding="utf-8")
        relifted = analyze(target_path, lang, target_fn.name, emitted_target=True)

        assert relifted.functions[0].semantic_mapping() == target_fn.semantic_mapping()
        assert _normalize_ir_for_comparison(relifted)["functions"][0]["body"] == _normalize_ir_for_comparison(ir_original)["functions"][0]["body"]
