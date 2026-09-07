"""Tests for loops and control flow: while, for, break, and continue statements."""
from __future__ import annotations

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import ROUTED_LANGUAGES, Language, RouteError
from elmos_polyglot_route.native import SemanticIR

_EMITTABLE: tuple[Language, ...] = ROUTED_LANGUAGES


def _name(value: str) -> dict:
    return {"kind": "name", "value": value}


def _literal(value: object) -> dict:
    return {"kind": "literal", "value": value}


def _binary(operator: str, left: dict, right: dict) -> dict:
    return {"kind": "binary", "operator": operator, "left": left, "right": right}


def _let(name: str, canonical_type: str, expression: dict) -> dict:
    return {"kind": "let", "name": name, "type": canonical_type, "expression": expression}


def _while(condition: dict, body: list[dict]) -> dict:
    return {"kind": "while", "condition": condition, "body": body}


def _for(name: str, start: dict, end: dict, body: list[dict], step: dict | None = None) -> dict:
    res = {
        "kind": "for",
        "name": name,
        "type": "integer",
        "start": start,
        "end": end,
        "body": body,
    }
    if step is not None:
        res["step"] = step
    return res


def _ir(body: list[dict], *, parameters: list[tuple[str, str]] | None = None) -> SemanticIR:
    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Subject.java",
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


def test_while_loop_ir_roundtrip() -> None:
    ir = _ir(
        [
            _while(
                _binary(">", _name("n"), _literal(0)),
                [
                    {"kind": "break"},
                ],
            ),
            {"kind": "return", "expression": _name("n")},
        ]
    )
    stmt = ir.functions[0].body[0]
    assert stmt.kind == "while"
    assert stmt.condition is not None
    assert len(stmt.body) == 1
    assert stmt.body[0].kind == "break"

    mapping = ir.to_mapping()
    roundtrip = SemanticIR.from_mapping(mapping)
    assert roundtrip.functions[0].body[0].kind == "while"
    assert roundtrip.functions[0].body[0].body[0].kind == "break"


def test_for_loop_ir_roundtrip() -> None:
    ir = _ir(
        [
            _for(
                "i",
                _literal(0),
                _name("n"),
                [
                    {"kind": "continue"},
                ],
                step=_literal(2),
            ),
            {"kind": "return", "expression": _name("n")},
        ]
    )
    stmt = ir.functions[0].body[0]
    assert stmt.kind == "for"
    assert stmt.name == "i"
    assert stmt.declared_type == "integer"
    assert stmt.step is not None
    assert len(stmt.body) == 1
    assert stmt.body[0].kind == "continue"

    mapping = ir.to_mapping()
    roundtrip = SemanticIR.from_mapping(mapping)
    assert roundtrip.functions[0].body[0].kind == "for"
    assert roundtrip.functions[0].body[0].name == "i"
    assert roundtrip.functions[0].body[0].body[0].kind == "continue"


def test_types_check_accepts_valid_loops() -> None:
    ir = _ir(
        [
            _let("sum", "integer", _literal(0)),
            _for(
                "i",
                _literal(0),
                _name("n"),
                [
                    _let("curr", "integer", _binary("+", _name("i"), _name("sum"))),
                    {"kind": "continue"},
                ],
            ),
            _while(
                _binary("<", _name("sum"), _name("n")),
                [
                    {"kind": "break"},
                ],
            ),
            {"kind": "return", "expression": _name("sum")},
        ]
    )
    types.check(ir)


def test_types_check_rejects_non_boolean_while_condition() -> None:
    ir = _ir(
        [
            _while(_literal(42), [{"kind": "break"}]),
            {"kind": "return", "expression": _name("n")},
        ]
    )
    with pytest.raises(RouteError, match="CONDITION_MUST_BE_BOOLEAN"):
        types.check(ir)


def test_types_check_rejects_non_integer_for_bounds() -> None:
    ir = _ir(
        [
            _for("i", _literal(3.14), _name("n"), [{"kind": "continue"}]),
            {"kind": "return", "expression": _name("n")},
        ]
    )
    with pytest.raises(RouteError, match="LOOP_BOUND_TYPE_MISMATCH:start:integer:number"):
        types.check(ir)


def test_types_check_rejects_shadowing_loop_variable() -> None:
    ir = _ir(
        [
            _for("n", _literal(0), _literal(10), [{"kind": "continue"}]),
            {"kind": "return", "expression": _name("n")},
        ]
    )
    with pytest.raises(RouteError, match="LET_NAME_ALREADY_BOUND:n"):
        types.check(ir)


def test_types_check_loop_variable_does_not_leak_outside() -> None:
    ir = _ir(
        [
            _for("i", _literal(0), _literal(10), [{"kind": "continue"}]),
            # `i` is not in environment after loop
            {"kind": "return", "expression": _name("i")},
        ]
    )
    with pytest.raises(RouteError, match="UNDECLARED_NAME:i"):
        types.check(ir)


def test_types_check_rejects_break_outside_loop() -> None:
    ir = _ir(
        [
            {"kind": "break"},
            {"kind": "return", "expression": _name("n")},
        ]
    )
    with pytest.raises(RouteError, match="BREAK_OUTSIDE_LOOP"):
        types.check(ir)


def test_types_check_rejects_continue_outside_loop() -> None:
    ir = _ir(
        [
            {"kind": "continue"},
            {"kind": "return", "expression": _name("n")},
        ]
    )
    with pytest.raises(RouteError, match="CONTINUE_OUTSIDE_LOOP"):
        types.check(ir)


@pytest.mark.parametrize("target", _EMITTABLE)
def test_every_emittable_target_spells_while_and_for(target: Language) -> None:
    ir = _ir(
        [
            _let("total", "integer", _literal(0)),
            _for(
                "idx",
                _literal(0),
                _name("n"),
                [
                    _while(
                        _binary(">", _name("idx"), _literal(5)),
                        [
                            {"kind": "break"},
                        ],
                    ),
                    {"kind": "continue"},
                ],
                step=_literal(2),
            ),
            {"kind": "return", "expression": _name("total")},
        ]
    )
    content = emit(ir, target).content
    assert "idx" in content
    assert "break" in content
    assert "continue" in content
    if target == "python":
        assert "for idx in range(0, n, 2):" in content
        assert "while (idx > 5):" in content
    elif target == "go":
        assert "for idx := int64(0); idx < n; idx += 2 {" in content
        assert "for (idx > 5) {" in content
    elif target == "java":
        assert "for (long idx = 0; idx < n; idx += 2) {" in content
        assert "while ((idx > 5)) {" in content
        assert "break;" in content
    elif target == "typescript":
        assert "for (let idx: number = 0; idx < n; idx += 2) {" in content
        assert "while ((idx > 5)) {" in content
        assert "break;" in content
    elif target == "rust":
        assert "for idx in (0..n).step_by(2 as usize) {" in content
        assert "while idx > 5 {" in content
        assert "break;" in content
