"""`let`: single-assignment local bindings.

The IR carried five statement/expression shapes -- `name`, `literal`,
`binary`, `return`, `if` -- which is why almost no real function fits the
profile: a function with any intermediate value has nowhere to put it. `let`
is the smallest widening that changes that, and it is the only one with no
cross-function, cross-file, exception or object-model consequences.

THREE DECISIONS WORTH KNOWING BEFORE CHANGING ANY OF THIS

*Single assignment, not assignment.* A name binds once and only for the
statements after it. Rebinding would make a function's meaning depend on
statement order in a way the equivalence model cannot compare, and the
profile's claim is that a function is a typed pure expression tree.

*Block scoping, deliberately the stricter rule.* Python binds a name for the
whole function, so `if c: x = 1` leaves `x` readable afterwards. Go, Rust,
Java, C#, C++ and Swift bind it to the block, where the same shape does not
compile. One IR cannot mean both, so it means the one that is safe in all of
them, and a source relying on Python's function scope is refused here rather
than emitted into a target that would not build.

*Declared type, not inferred.* The frontend has already resolved the type
against its own language. Writing it into the IR is what lets `types.check`
disagree instead of silently adopting whatever the expression produced.
"""
from __future__ import annotations

import pytest

from elmos_polyglot_route import types
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.identifier_hygiene import plan_identifiers
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
                        for item, kind in (parameters if parameters is not None else [("a", "integer")])
                    ],
                    "body": body,
                }
            ],
        }
    )


def _two_bindings() -> SemanticIR:
    return _ir(
        [
            _let("half", "integer", _binary("/", _name("w"), _literal(2))),
            _let("scaled", "integer", _binary("*", _name("half"), _name("h"))),
            {"kind": "return", "expression": _binary("+", _name("scaled"), _literal(1))},
        ],
        parameters=[("w", "integer"), ("h", "integer")],
    )


def test_a_let_survives_the_ir_round_trip() -> None:
    ir = _two_bindings()
    statement = ir.functions[0].body[0]

    assert statement.kind == "let"
    assert statement.name == "half"
    assert statement.declared_type == "integer"
    assert SemanticIR.from_mapping(ir.to_mapping()).functions[0].body[1].name == "scaled"
    assert ir.functions[0].body[0].semantic_mapping()["type"] == "integer"


def test_a_binding_is_visible_to_the_statements_after_it() -> None:
    types.check(_two_bindings())


@pytest.mark.parametrize("target", _EMITTABLE)
def test_every_emittable_target_spells_a_binding(target: Language) -> None:
    content = emit(_two_bindings(), target).content
    assert "half" in content
    assert "scaled" in content


@pytest.mark.parametrize(
    ("target", "keyword"),
    [
        ("java", "final "),
        ("rust", "let "),
        ("swift", "let "),
        ("kotlin", "val "),
        ("typescript", "const "),
        ("cpp", "const "),
        ("objc", "const "),
    ],
)
def test_a_target_with_an_immutability_keyword_uses_it(target: Language, keyword: str) -> None:
    """The IR guarantees single assignment; a target that can say so should.

    It keeps the emitted file honest for a human reader, and it lets the
    target's own compiler enforce what the IR only promises.
    """
    assert keyword in emit(_two_bindings(), target).content


def test_a_binding_that_leaks_out_of_a_branch_is_refused() -> None:
    """The Python-versus-everything-else scope divergence, asserted directly.

    `if c: x = 1` then reading `x` afterwards is ordinary Python and a
    compile error in six of the other targets. Accepting it would emit files
    that do not build.
    """
    ir = _ir(
        [
            {
                "kind": "if",
                "condition": _binary(">", _name("a"), _literal(0)),
                "then": [_let("t", "integer", _literal(1))],
                "else": [],
            },
            {"kind": "return", "expression": _name("t")},
        ]
    )
    with pytest.raises(RouteError, match="UNDECLARED_NAME:t"):
        types.check(ir)


def test_a_binding_used_inside_its_own_branch_is_fine() -> None:
    ir = _ir(
        [
            {
                "kind": "if",
                "condition": _binary(">", _name("a"), _literal(0)),
                "then": [
                    _let("t", "integer", _binary("*", _name("a"), _literal(2))),
                    {"kind": "return", "expression": _name("t")},
                ],
                "else": [{"kind": "return", "expression": _literal(0)}],
            }
        ]
    )
    types.check(ir)
    assert "t" in emit(ir, "go").content


def test_a_binding_may_not_shadow_a_parameter() -> None:
    ir = _ir([_let("a", "integer", _literal(1)), {"kind": "return", "expression": _name("a")}])
    with pytest.raises(RouteError, match="LET_NAME_ALREADY_BOUND:a"):
        types.check(ir)


def test_a_name_may_not_be_bound_twice() -> None:
    ir = _ir(
        [
            _let("x", "integer", _literal(1)),
            _let("x", "integer", _literal(2)),
            {"kind": "return", "expression": _name("x")},
        ]
    )
    with pytest.raises(RouteError, match="LET_NAME_ALREADY_BOUND:x"):
        types.check(ir)


def test_a_declared_type_that_disagrees_with_the_expression_is_refused() -> None:
    """No integer -> number widening here, unlike `return`.

    A `return` may widen because every target widens identically at that
    boundary. A binding names a value, and letting the name disagree with the
    value is how a later expression silently changes which arithmetic rules
    apply to it.
    """
    ir = _ir([_let("x", "number", _literal(1)), {"kind": "return", "expression": _literal(0)}])
    with pytest.raises(RouteError, match="LET_TYPE_MISMATCH:number:integer"):
        types.check(ir)


def test_a_binding_cannot_refer_to_itself() -> None:
    ir = _ir(
        [
            _let("x", "integer", _binary("+", _name("x"), _literal(1))),
            {"kind": "return", "expression": _name("x")},
        ]
    )
    with pytest.raises(RouteError, match="UNDECLARED_NAME:x"):
        types.check(ir)


@pytest.mark.parametrize(
    ("local", "target"),
    [("final", "java"), ("var", "go"), ("match", "rust"), ("val", "kotlin"), ("class", "python")],
)
def test_a_local_named_like_a_target_keyword_is_alpha_renamed(local: str, target: Language) -> None:
    ir = _ir(
        [_let(local, "integer", _binary("+", _name("a"), _literal(1))), {"kind": "return", "expression": _name(local)}]
    )
    binding = next(
        item for item in plan_identifiers(ir, target).to_mapping()["bindings"] if item["role"] == "local"
    )

    assert binding["decision"] != "PRESERVED"
    assert binding["target_name"].startswith("elmos_l")
    assert "TARGET_RESERVED" in binding["candidates_examined"][0]["reasons"]


def test_a_generated_local_name_is_distinguishable_from_a_parameter() -> None:
    """`elmos_p...` and `elmos_l...` say which binder produced the name.

    A local and a parameter share one target scope, so a reader of the emitted
    file has no other way to tell them apart.
    """
    ir = _ir(
        [_let("var", "integer", _binary("+", _name("a"), _literal(1))), {"kind": "return", "expression": _name("var")}]
    )
    bindings = plan_identifiers(ir, "go").to_mapping()["bindings"]
    local = next(item for item in bindings if item["role"] == "local")

    assert local["target_name"].startswith("elmos_l000_")


def test_locals_and_parameters_are_allocated_against_one_scope() -> None:
    """They share a scope in the target, so they must share a collision map.

    A local that took a parameter's target name would shadow it in every brace
    language and be a redeclaration error in several.
    """
    ir = _ir(
        [_let("b", "integer", _name("a")), {"kind": "return", "expression": _name("b")}],
        parameters=[("a", "integer")],
    )
    bindings = plan_identifiers(ir, "go").to_mapping()["bindings"]
    scoped = [item for item in bindings if item["role"] in {"parameter", "local"}]

    assert len({item["scope_id"] for item in scoped}) == 1
    assert len({item["target_name"] for item in scoped}) == len(scoped)


def test_an_unbound_reference_is_still_refused() -> None:
    ir = _ir([{"kind": "return", "expression": _name("missing")}])
    with pytest.raises(RouteError, match="UNDECLARED_NAME:missing"):
        types.check(ir)
