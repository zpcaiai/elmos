from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from elmos_polyglot_route import emitter, types
from elmos_polyglot_route.identifier_hygiene import alpha_normalize_target, plan_identifiers
from elmos_polyglot_route.models import (
    Expression,
    Function,
    Parameter,
    RouteError,
    SemanticIR,
    Statement,
)
from elmos_polyglot_route.python_analyzer import analyze_python


def _make_ir(functions: list[Function]) -> SemanticIR:
    return SemanticIR(
        source_language="python",
        source_file="sample.py",
        analyzer="CPython ast",
        analyzer_version="3.12",
        functions=tuple(functions),
        records=(),
        diagnostics=(),
    )


def test_call_expression_wire_and_semantic_mapping():
    call_expr = Expression(
        kind="call",
        function_name="helper",
        call_arguments=(
            Expression(kind="name", value="x"),
            Expression(kind="literal", value=42),
        ),
    )
    mapping = call_expr.to_mapping()
    assert mapping == {
        "kind": "call",
        "function_name": "helper",
        "arguments": [
            {"kind": "name", "value": "x"},
            {"kind": "literal", "value": 42},
        ],
    }
    restored = Expression.from_mapping(mapping)
    assert restored.kind == "call"
    assert restored.function_name == "helper"
    assert len(restored.call_arguments) == 2
    assert restored.call_arguments[0].value == "x"
    assert restored.call_arguments[1].value == 42


def test_types_infer_call_and_checks():
    helper_fn = Function(
        name="helper",
        parameters=(
            Parameter(name="a", type="integer"),
            Parameter(name="b", type="number"),
        ),
        return_type="number",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="binary",
                    operator="+",
                    left=Expression(kind="name", value="a"),
                    right=Expression(kind="name", value="b"),
                ),
            ),
        ),
    )
    caller_fn = Function(
        name="caller",
        parameters=(Parameter(name="x", type="integer"),),
        return_type="number",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="call",
                    function_name="helper",
                    call_arguments=(
                        Expression(kind="name", value="x"),
                        Expression(kind="literal", value=10),  # integer widened to number
                    ),
                ),
            ),
        ),
    )
    ir = _make_ir([helper_fn, caller_fn])
    # check passes
    types.check(ir)

    # Arity mismatch
    bad_arity_fn = Function(
        name="bad_caller",
        parameters=(Parameter(name="x", type="integer"),),
        return_type="number",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="call",
                    function_name="helper",
                    call_arguments=(Expression(kind="name", value="x"),),
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="FUNCTION_CALL_ARITY_MISMATCH"):
        types.check(_make_ir([helper_fn, bad_arity_fn]))

    # Type mismatch
    bad_type_fn = Function(
        name="bad_type_caller",
        parameters=(Parameter(name="s", type="string"),),
        return_type="number",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="call",
                    function_name="helper",
                    call_arguments=(
                        Expression(kind="name", value="s"),
                        Expression(kind="literal", value=1.0),
                    ),
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="ARGUMENT_TYPE_MISMATCH"):
        types.check(_make_ir([helper_fn, bad_type_fn]))

    # Unknown function
    unknown_fn = Function(
        name="unknown_caller",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="call",
                    function_name="nonexistent",
                    call_arguments=(),
                ),
            ),
        ),
    )
    with pytest.raises(RouteError, match="UNKNOWN_FUNCTION:nonexistent"):
        types.check(_make_ir([unknown_fn]))


def test_topological_sort_and_recursion_cycle_rejection():
    fn_c = Function(
        name="fn_c",
        parameters=(),
        return_type="integer",
        body=(Statement(kind="return", expression=Expression(kind="literal", value=1)),),
    )
    fn_b = Function(
        name="fn_b",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(kind="call", function_name="fn_c", call_arguments=()),
            ),
        ),
    )
    fn_a = Function(
        name="fn_a",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(kind="call", function_name="fn_b", call_arguments=()),
            ),
        ),
    )

    # Topological sort orders callees before callers: fn_c, fn_b, fn_a
    sorted_fns = types.topological_sort_functions((fn_a, fn_b, fn_c))
    assert [f.name for f in sorted_fns] == ["fn_c", "fn_b", "fn_a"]

    # Direct recursion f -> f rejected
    recursive_self = Function(
        name="rec_self",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(kind="call", function_name="rec_self", call_arguments=()),
            ),
        ),
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET:rec_self->rec_self"):
        types.topological_sort_functions((recursive_self,))

    # Mutual recursion f -> g -> f rejected
    mut_f = Function(
        name="mut_f",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(kind="call", function_name="mut_g", call_arguments=()),
            ),
        ),
    )
    mut_g = Function(
        name="mut_g",
        parameters=(),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(kind="call", function_name="mut_f", call_arguments=()),
            ),
        ),
    )
    with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET"):
        types.topological_sort_functions((mut_f, mut_g))


def test_python_analyzer_direct_calls():
    code = '''
def double_val(x: int) -> int:
    return x * 2

def compute(a: int, b: int) -> int:
    return double_val(a) + double_val(b)
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "math_mod.py"
        src.write_text(code.strip())
        ir = analyze_python(src, "compute")
        assert len(ir.functions) == 2
        # topological sort puts callee first
        assert [f.name for f in ir.functions] == ["double_val", "compute"]


def test_python_analyzer_recursion_rejected():
    code = '''
def loop_fn(x: int) -> int:
    return loop_fn(x - 1)
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        src = Path(tmpdir) / "rec.py"
        src.write_text(code.strip())
        with pytest.raises(RouteError, match="RECURSIVE_CALL_OUTSIDE_CERTIFIED_SUBSET:loop_fn->loop_fn"):
            analyze_python(src, "loop_fn")


def test_emitter_topological_multicall():
    helper_fn = Function(
        name="helper",
        parameters=(Parameter(name="x", type="integer"),),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="binary",
                    operator="+",
                    left=Expression(kind="name", value="x"),
                    right=Expression(kind="literal", value=1),
                ),
            ),
        ),
    )
    caller_fn = Function(
        name="caller",
        parameters=(Parameter(name="x", type="integer"),),
        return_type="integer",
        body=(
            Statement(
                kind="return",
                expression=Expression(
                    kind="call",
                    function_name="helper",
                    call_arguments=(Expression(kind="name", value="x"),),
                ),
            ),
        ),
    )
    ir = _make_ir([caller_fn, helper_fn])  # caller before helper in raw IR

    # Emitting for python: helper should be emitted before caller
    emitted_py = emitter.emit(ir, "python")
    code_py = emitted_py.content
    assert code_py.index("def helper(") < code_py.index("def caller(")

    # Emitting for typescript: helper should be emitted before caller
    emitted_ts = emitter.emit(ir, "typescript")
    code_ts = emitted_ts.content
    assert code_ts.index("function helper(") < code_ts.index("function caller(")

    # Emitting for go: helper and caller both emitted
    emitted_go = emitter.emit(ir, "go")
    code_go = emitted_go.content
    assert "func helper(" in code_go and "func caller(" in code_go

    # Emitting for cpp: helper must appear before caller for forward declaration free compilation
    emitted_cpp = emitter.emit(ir, "cpp")
    code_cpp = emitted_cpp.content
    plan_cpp = plan_identifiers(ir, "cpp")
    fn_map = {b.source_name: b.target_name for b in plan_cpp.bindings if b.role == "function"}
    assert code_cpp.index(f"std::int64_t {fn_map['helper']}(") < code_cpp.index(f"std::int64_t {fn_map['caller']}(")


