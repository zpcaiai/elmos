"""Lifting `let` *from* Python -- the step that turns the IR's local binding
from a feature nobody produces into an actual widening of the accepted subset.

Before this, `let` existed in models/types/emitter/identifier_hygiene and in
34 tests, and `grep -rln '"let"' native/ python_analyzer.py` came back empty:
no analyzer emitted one, so the range of real source the engine accepted had
not moved at all. These tests are what make the claim checkable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.discovery import Verdict, discover_repository
from elmos_polyglot_route.emitter import emit
from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.python_analyzer import analyze_python
from elmos_polyglot_route.repository import plan_repository


def _source(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "source.py"
    path.write_text(body, encoding="utf-8")
    return path


def test_an_annotated_local_lifts_to_a_let(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "def total(price: int, tax: int) -> int:\n"
        "    subtotal: int = price + tax\n"
        "    return subtotal\n",
    )
    semantic = analyze_python(source, "total")
    statements = semantic.functions[0].body
    assert statements[0].kind == "let"
    assert statements[0].name == "subtotal"
    assert statements[0].declared_type == "integer"
    assert statements[0].expression is not None
    assert statements[0].expression.operator == "+"


def test_the_lifted_let_reaches_every_target(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "def total(price: int, tax: int) -> int:\n"
        "    subtotal: int = price + tax\n"
        "    return subtotal\n",
    )
    semantic = analyze_python(source, "total")
    # One spelling per language family: a declared type where the language
    # wants one, `const`/`val`/`let` where that is the idiom.
    assert "final long" in emit(semantic, "java").content
    assert "var " in emit(semantic, "go").content
    assert "let " in emit(semantic, "rust").content
    assert "val " in emit(semantic, "kotlin").content


def test_an_unannotated_assignment_says_what_to_do(tmp_path: Path) -> None:
    # Deliberately its own code rather than PYTHON_UNSUPPORTED_STATEMENT:Assign,
    # which would read as "assignment is unsupported" -- no longer true.
    source = _source(
        tmp_path,
        "def total(price: int) -> int:\n    subtotal = price\n    return subtotal\n",
    )
    with pytest.raises(RouteError, match="^PYTHON_UNANNOTATED_ASSIGNMENT_OUTSIDE_CERTIFIED_SUBSET$"):
        analyze_python(source, "total")


def test_a_declaration_without_a_value_is_not_a_binding(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "def total(price: int) -> int:\n    subtotal: int\n    return price\n",
    )
    with pytest.raises(RouteError, match="^PYTHON_ANNOTATED_DECLARATION_WITHOUT_VALUE$"):
        analyze_python(source, "total")


@pytest.mark.parametrize(
    "statement",
    [
        "(subtotal): int = price",   # parenthesised: node.simple is 0
        "holder.subtotal: int = price",
        "holder[0]: int = price",
    ],
)
def test_only_a_plain_name_can_be_bound(statement: str, tmp_path: Path) -> None:
    source = _source(tmp_path, f"def total(price: int) -> int:\n    {statement}\n    return price\n")
    with pytest.raises(RouteError, match="^PYTHON_ASSIGNMENT_TARGET_OUTSIDE_CERTIFIED_SUBSET$"):
        analyze_python(source, "total")


def test_an_uncanonical_annotation_names_itself(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "def total(price: int) -> int:\n    parts: list = price\n    return price\n",
    )
    with pytest.raises(RouteError, match="^PYTHON_UNSUPPORTED_LOCAL_TYPE:list$"):
        analyze_python(source, "total")


def test_the_declared_type_is_held_against_the_value(tmp_path: Path) -> None:
    # The annotation is not decoration: types.check disagrees with it rather
    # than adopting whatever the initializer produced.
    source = _source(
        tmp_path,
        "def total(price: int) -> int:\n    subtotal: int = 1.5\n    return price\n",
    )
    with pytest.raises(RouteError, match="^LET_TYPE_MISMATCH:integer:number$"):
        analyze_python(source, "total")


def test_a_local_may_not_shadow_a_parameter(tmp_path: Path) -> None:
    source = _source(
        tmp_path,
        "def total(price: int) -> int:\n    price: int = 1\n    return price\n",
    )
    with pytest.raises(RouteError, match="^LET_NAME_ALREADY_BOUND:price$"):
        analyze_python(source, "total")


def test_a_binding_made_inside_a_branch_does_not_escape_it(tmp_path: Path) -> None:
    """Python would allow this; the IR is block-scoped on purpose.

    `if c: x = 1` leaves `x` readable after the `if` in Python and in no brace
    language. Lifting it would emit something that does not compile in Go,
    Rust, Java, C#, C++ or Swift, so it is refused here instead.
    """
    source = _source(
        tmp_path,
        "def total(price: int) -> int:\n"
        "    if price > 0:\n"
        "        bonus: int = 1\n"
        "    return bonus\n",
    )
    with pytest.raises(RouteError, match="^UNDECLARED_NAME:bonus$"):
        analyze_python(source, "total")


def test_python_only_arithmetic_is_still_caught_through_a_local(tmp_path: Path) -> None:
    """The regression the scope tracking in `_check_statements` exists for.

    `/` on two integers is rejected by inferring both operand types. With the
    left operand bound by a `let`, an analyzer that did not carry the binding
    would raise UNDECLARED_NAME -- the right outcome for the wrong reason, and
    the wrong outcome the moment the operands are floats.
    """
    source = _source(
        tmp_path,
        "def divide(b: int) -> int:\n    a: int = 7\n    return a / b\n",
    )
    with pytest.raises(RouteError, match="^PYTHON_TRUE_DIVISION_ON_INTEGERS_OUTSIDE_CERTIFIED_SUBSET$"):
        analyze_python(source, "divide")


def test_a_float_local_still_divides(tmp_path: Path) -> None:
    # The other half: with the binding carried, float division is judged on its
    # operand types and stays in the subset.
    source = _source(
        tmp_path,
        "def ratio(b: float) -> float:\n    a: float = 7.0\n    return a / b\n",
    )
    semantic = analyze_python(source, "ratio")
    assert "elmosNonZero" in emit(semantic, "java").content


@pytest.mark.parametrize(
    ("source", "diagnostic"),
    [
        (
            "def choose(value: int) -> int:\n"
            "    if value:\n"
            "        return value\n"
            "    return 0\n",
            "CONDITION_MUST_BE_BOOLEAN",
        ),
        (
            "def total(value: int, value: int) -> int:\n    return value\n",
            "DUPLICATE_PARAMETER:value",
        ),
        (
            "def total(value: int) -> int:\n    return value + True\n",
            "OPERAND_TYPE_MISMATCH:+:integer:boolean",
        ),
        (
            'def label(value: int) -> int:\n    return "label"\n',
            "RETURN_TYPE_MISMATCH:integer:string",
        ),
        (
            "def before(left: str, right: str) -> bool:\n    return left < right\n",
            "STRING_ORDERING_OUTSIDE_CERTIFIED_SUBSET:<",
        ),
    ],
)
def test_discovery_classifies_canonical_python_type_rejections_as_unsupported(
    source: str,
    diagnostic: str,
    tmp_path: Path,
) -> None:
    repository = tmp_path / "python-type-rejection"
    repository.mkdir()
    (repository / "source.py").write_text(source, encoding="utf-8")

    report = discover_repository(
        plan_repository(
            repository,
            "local:python-type-rejection",
            "python",
            "typescript",
        ),
        repository,
    )

    assert report["verdict_counts"] == {Verdict.UNSUPPORTED: 1}
    [blocked] = report["results"]
    assert blocked["verdict"] == Verdict.UNSUPPORTED
    assert blocked["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert diagnostic in blocked["reason"]


def test_discovery_keeps_a_lifted_binding_ready_and_classifies_its_peers(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "python-local-bindings"
    repository.mkdir()
    (repository / "pricing.py").write_text(
        "def total(price: int, tax: int) -> int:\n"
        "    subtotal: int = price + tax\n"
        "    return subtotal\n\n"
        "def untyped(price: int) -> int:\n"
        "    subtotal = price\n"
        "    return subtotal\n\n"
        "def mistyped(price: int) -> int:\n"
        "    subtotal: int = price + True\n"
        "    return subtotal\n",
        encoding="utf-8",
    )

    report = discover_repository(
        plan_repository(
            repository,
            "local:python-local-bindings",
            "python",
            "typescript",
        ),
        repository,
    )

    results = {result["source_symbol"]["name"]: result for result in report["results"]}
    assert results["total"]["verdict"] == Verdict.READY
    assert results["untyped"]["verdict"] == Verdict.UNSUPPORTED
    assert results["untyped"]["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert results["mistyped"]["verdict"] == Verdict.UNSUPPORTED
    assert results["mistyped"]["blocker_code"] == "NATIVE_ANALYZER_REJECTED"
    assert "OPERAND_TYPE_MISMATCH:+:integer:boolean" in results["mistyped"]["reason"]
    assert report["verdict_counts"] == {
        Verdict.READY: 1,
        Verdict.UNSUPPORTED: 2,
    }
