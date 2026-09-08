"""Tests for mutable assignment (`assign`) in Canonical IR, Typechecker, Emitter, and Python Analyzer."""
from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import ROUTED_LANGUAGES, Language, RouteError
from elmos_polyglot_route.native import SemanticIR
from elmos_polyglot_route.python_analyzer import analyze_python

_EMITTABLE: tuple[Language, ...] = ROUTED_LANGUAGES


def _name(value: str) -> dict:
    return {"kind": "name", "value": value}


def _literal(value: object) -> dict:
    return {"kind": "literal", "value": value}


def _binary(operator: str, left: dict, right: dict) -> dict:
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def _let(name: str, canonical_type: str, expression: dict) -> dict:
    return {"kind": "let", "name": name, "type": canonical_type, "expression": expression}


def _assign(name: str, expression: dict) -> dict:
    return {"kind": "assign", "name": name, "expression": expression}


def _ir(body: list[dict], *, parameters: list[tuple[str, str]] | None = None) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "python",
            "source_file": "subject.py",
            "analyzer": "test",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": "subject",
                    "return_type": "integer",
                    "parameters": [
                        {"name": item, "type": kind}
                        for item, kind in (parameters if parameters is not None else [("n", "integer")])
                    ],
                    "body": body,
                }
            ],
        }
    )


def _accumulator_ir() -> SemanticIR:
    return _ir(
        [
            _let("limit", "integer", _literal(10)),
            _let("total", "integer", _literal(0)),
            {
                "kind": "for",
                "name": "i",
                "type": "integer",
                "start": _literal(0),
                "end": _name("n"),
                "body": [
                    _assign("total", _binary("+", _name("total"), _name("i"))),
                ],
            },
            {"kind": "return", "expression": _binary("+", _name("total"), _name("limit"))},
        ],
        parameters=[("n", "integer")],
    )


def test_assign_ir_round_trip() -> None:
    ir = _accumulator_ir()
    func = ir.functions[0]
    let_total = func.body[1]
    assert let_total.kind == "let"
    assert let_total.name == "total"

    for_stmt = func.body[2]
    assert for_stmt.kind == "for"
    assert len(for_stmt.body) == 1

    assign_stmt = for_stmt.body[0]
    assert assign_stmt.kind == "assign"
    assert assign_stmt.name == "total"
    assert assign_stmt.expression is not None
    assert assign_stmt.expression.kind == "binary"

    # Check to_mapping and from_mapping preserve assign
    mapping = ir.to_mapping()
    reconstructed = SemanticIR.from_mapping(mapping)
    reconstructed_assign = reconstructed.functions[0].body[2].body[0]
    assert reconstructed_assign.kind == "assign"
    assert reconstructed_assign.name == "total"

    # Check semantic_mapping
    sem = assign_stmt.semantic_mapping()
    assert sem["kind"] == "assign"
    assert sem["name"] == "total"
    assert sem["expression"]["kind"] == "binary"


def test_assign_type_checks_cleanly() -> None:
    types.check(_accumulator_ir())


def test_assign_to_unbound_variable_fails() -> None:
    ir = _ir([
        _assign("unbound", _literal(42)),
        {"kind": "return", "expression": _literal(0)},
    ])
    with pytest.raises(RouteError, match="^ASSIGN_NAME_NOT_BOUND:unbound$"):
        types.check(ir)


def test_assign_type_mismatch_fails() -> None:
    ir = _ir([
        _let("count", "integer", _literal(0)),
        _assign("count", _literal(True)),
        {"kind": "return", "expression": _name("count")},
    ])
    with pytest.raises(RouteError, match="^ASSIGN_TYPE_MISMATCH:integer:boolean$"):
        types.check(ir)


def test_assign_inside_if_branches_to_outer_var() -> None:
    ir = _ir([
        _let("res", "integer", _literal(0)),
        {
            "kind": "if",
            "condition": _binary(">", _name("n"), _literal(0)),
            "then": [
                _assign("res", _literal(1)),
            ],
            "else": [
                _assign("res", _literal(-1)),
            ],
        },
        {"kind": "return", "expression": _name("res")},
    ])
    types.check(ir)


@pytest.mark.parametrize("target", _EMITTABLE)
def test_mutable_variable_uses_mutable_spelling_across_all_targets(target: Language) -> None:
    content = emit(_accumulator_ir(), target).content

    # 'limit' is never assigned, so it must keep immutable spelling where available
    # 'total' is assigned, so it must use mutable spelling
    if target == "rust":
        assert "let limit: i64 = 10;" in content
        assert "let mut total: i64 = 0;" in content
        assert "total = " in content
    elif target == "swift":
        assert "let limit: Int64 = Int64(10)" in content
        assert "var total: Int64 = Int64(0)" in content
        assert "total = " in content
    elif target == "kotlin":
        assert "val limit: Long = 10L" in content
        assert "var total: Long = 0L" in content
        assert "total = " in content
    elif target in {"typescript", "react"}:
        assert "const limit: number = 10;" in content
        assert "let total: number = 0;" in content
        assert "total = " in content
    elif target == "javascript":
        assert "const limit = 10;" in content
        assert "let total = 0;" in content
        assert "total = " in content
    elif target == "java":
        assert "final long limit = 10;" in content
        assert "long total = 0;" in content
        assert "total = " in content
    elif target == "cpp":
        assert "const std::int64_t limit = 10;" in content
        assert "std::int64_t total = 0;" in content
        assert "total = " in content
    elif target == "objc":
        assert "const long long limit = 10;" in content
        assert "long long total = 0;" in content
        assert "total = " in content
    elif target == "flutter":
        assert "final int limit = 10;" in content
        assert "int total = 0;" in content
        assert "total = " in content
    elif target == "go":
        assert "var limit int64 = 10" in content
        assert "var total int64 = 0" in content
        assert "total = " in content
    elif target == "python":
        assert "limit: int = 10" in content
        assert "total: int = 0" in content
        assert "total = " in content
    elif target == "csharp":
        assert "long limit = 10;" in content
        assert "long total = 0;" in content
        assert "total = " in content
    elif target == "php":
        assert "$limit = 10;" in content
        assert "$total = 0;" in content
        assert "$total = " in content


def _write_py(tmp_path: Path, code: str) -> Path:
    p = tmp_path / "test_fn.py"
    p.write_text(code, encoding="utf-8")
    return p


def test_python_analyzer_lifts_assign(tmp_path: Path) -> None:
    source = _write_py(
        tmp_path,
        "def run(n: int) -> int:\n"
        "    s: int = 0\n"
        "    for i in range(n):\n"
        "        s = s + i\n"
        "    return s\n",
    )
    ir = analyze_python(source, "run")
    assert len(ir.functions) == 1
    func = ir.functions[0]
    for_stmt = func.body[1]
    assert for_stmt.kind == "for"
    assert len(for_stmt.body) == 1
    assert for_stmt.body[0].kind == "assign"
    assert for_stmt.body[0].name == "s"


def test_python_analyzer_lifts_aug_assign(tmp_path: Path) -> None:
    source = _write_py(
        tmp_path,
        "def run(n: int) -> int:\n"
        "    s: int = 0\n"
        "    for i in range(n):\n"
        "        s += i\n"
        "    return s\n",
    )
    ir = analyze_python(source, "run")
    func = ir.functions[0]
    for_stmt = func.body[1]
    assign_stmt = for_stmt.body[0]
    assert assign_stmt.kind == "assign"
    assert assign_stmt.name == "s"
    assert assign_stmt.expression.kind == "binary"
    assert assign_stmt.expression.operator == "+"
    assert assign_stmt.expression.left.value == "s"
    assert assign_stmt.expression.right.value == "i"


def test_python_analyzer_forbids_parameter_reassignment(tmp_path: Path) -> None:
    source = _write_py(
        tmp_path,
        "def run(x: int) -> int:\n"
        "    x = x + 1\n"
        "    return x\n",
    )
    with pytest.raises(RouteError, match="^PYTHON_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:x$"):
        analyze_python(source, "run")


def test_python_analyzer_forbids_aug_assign_on_parameter(tmp_path: Path) -> None:
    source = _write_py(
        tmp_path,
        "def run(x: int) -> int:\n"
        "    x += 1\n"
        "    return x\n",
    )
    with pytest.raises(RouteError, match="^PYTHON_PARAMETER_REASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET:x$"):
        analyze_python(source, "run")


def test_python_analyzer_emitted_target_roundtrip(tmp_path: Path) -> None:
    source = _write_py(
        tmp_path,
        "def accumulate(n: int) -> int:\n"
        "    acc: int = 0\n"
        "    for i in range(n):\n"
        "        acc += i\n"
        "    return acc\n",
    )
    ir = analyze_python(source, "accumulate")
    emitted = emit(ir, "python")

    emitted_file = tmp_path / emitted.relative_path
    emitted_file.write_text(emitted.content, encoding="utf-8")

    reanalyzed = analyze_python(emitted_file, "accumulate", emitted_target=True)
    assert reanalyzed.functions[0].name == "accumulate"
    assert len(reanalyzed.functions[0].body) == 3
    assert reanalyzed.functions[0].body[0].kind == "let"
    assert reanalyzed.functions[0].body[1].kind == "for"
    assert reanalyzed.functions[0].body[1].body[0].kind == "assign"
    assert reanalyzed.functions[0].body[2].kind == "return"
