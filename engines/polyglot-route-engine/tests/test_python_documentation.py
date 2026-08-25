"""A docstring must not cost a function its place in the bounded subset.

A Python docstring is a bare string expression, so it used to hit the generic
`PYTHON_UNSUPPORTED_STATEMENT:Expr` rejection and take the whole function with
it -- including functions whose signature and body were otherwise entirely
inside `typed-pure-function-v1`.

Measured on 20 real PyPI projects (583 non-test files, 7.06 MB), 94 of the 109
candidates that had already cleared the type gate died on exactly this: the
single largest avoidable rejection in the Python frontend.

The text is not thrown away. It is carried as `Function.documentation`, which
is deliberately PROVENANCE rather than semantics:

  * it appears in `to_mapping`, so nothing the source declared is silently lost
    and the recorded IR digest reflects it;
  * it is absent from `semantic_mapping`, so cross-language equivalence is
    never asked to compare a Python `__doc__` against a Java method that has no
    such concept;
  * a function with no docstring serializes byte-identically to before the
    field existed, so IR digests recorded earlier still hold.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from elmos_polyglot_route.models import RouteError, SemanticIR
from elmos_polyglot_route.python_analyzer import analyze_python

_DOCUMENTED = '''def calculate(quantity: int, price: int) -> int:
    """Return the line total."""
    return quantity * price
'''

_UNDOCUMENTED = '''def calculate(quantity: int, price: int) -> int:
    return quantity * price
'''


def _write(tmp_path: Path, body: str, name: str = "source.py") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_a_docstring_no_longer_rejects_an_otherwise_admissible_function(
    tmp_path: Path,
) -> None:
    ir = analyze_python(_write(tmp_path, _DOCUMENTED), "calculate")
    function = ir.functions[0]
    assert function.documentation == "Return the line total."
    # The docstring is removed from the executable body, not counted as a statement.
    assert [statement.kind for statement in function.body] == ["return"]


def test_documentation_is_provenance_and_never_changes_the_semantics(
    tmp_path: Path,
) -> None:
    documented = analyze_python(_write(tmp_path, _DOCUMENTED, "a.py"), "calculate")
    undocumented = analyze_python(_write(tmp_path, _UNDOCUMENTED, "b.py"), "calculate")
    assert (
        documented.functions[0].semantic_mapping()
        == undocumented.functions[0].semantic_mapping()
    )


def test_an_undocumented_function_serializes_exactly_as_before_the_field_existed(
    tmp_path: Path,
) -> None:
    """Guards every IR digest recorded before `documentation` was introduced."""

    mapping = analyze_python(_write(tmp_path, _UNDOCUMENTED), "calculate").to_mapping()
    assert "documentation" not in mapping["functions"][0]
    assert set(mapping["functions"][0]) == {"name", "parameters", "return_type", "body"}


def test_documentation_round_trips_through_the_ir_including_awkward_text(
    tmp_path: Path,
) -> None:
    awkward = (
        'def calculate(quantity: int, price: int) -> int:\n'
        '    """Line one.\n'
        '\n'
        '    Line two with "quotes", a backslash \\\\ and a unicode dash —.\n'
        '    """\n'
        '    return quantity * price\n'
    )
    mapping = analyze_python(_write(tmp_path, awkward), "calculate").to_mapping()
    reloaded = SemanticIR.from_mapping(mapping)
    assert reloaded.to_mapping() == mapping
    assert '"quotes"' in (reloaded.functions[0].documentation or "")


def test_an_empty_docstring_stays_distinguishable_from_having_none(
    tmp_path: Path,
) -> None:
    source = 'def calculate(quantity: int, price: int) -> int:\n    ""\n    return quantity * price\n'
    assert analyze_python(_write(tmp_path, source), "calculate").functions[0].documentation == ""
    assert analyze_python(_write(tmp_path, _UNDOCUMENTED, "b.py"), "calculate").functions[0].documentation is None


def test_a_body_that_is_only_a_docstring_fails_closed_with_its_own_code(
    tmp_path: Path,
) -> None:
    source = 'def calculate(quantity: int, price: int) -> int:\n    """Nothing here."""\n'
    with pytest.raises(RouteError) as raised:
        analyze_python(_write(tmp_path, source), "calculate")
    assert "PYTHON_FUNCTION_BODY_IS_ONLY_DOCUMENTATION" in str(raised.value)


@pytest.mark.parametrize(
    ("label", "source"),
    [
        (
            "not-the-first-statement",
            'def calculate(quantity: int, price: int) -> int:\n'
            '    x: int = 1\n'
            '    "stray"\n'
            '    return quantity * price\n',
        ),
        (
            "bytes-literal",
            'def calculate(quantity: int, price: int) -> int:\n'
            '    b"bytes"\n'
            '    return quantity * price\n',
        ),
    ],
)
def test_only_a_leading_string_literal_counts_as_documentation(
    tmp_path: Path, label: str, source: str
) -> None:
    """A bare string anywhere else is a no-op expression, not documentation."""

    with pytest.raises(RouteError) as raised:
        analyze_python(_write(tmp_path, source, f"{label}.py"), "calculate")
    assert "PYTHON_UNSUPPORTED_STATEMENT" in str(raised.value)


def test_the_emitted_target_reanalysis_gate_still_refuses_a_docstring(
    tmp_path: Path,
) -> None:
    """The widening is source-side only.

    This engine's emitters never produce a docstring, so one appearing in a
    target means the target did not come from them -- which is precisely what
    the re-analysis gate exists to catch. Accepting it there would weaken it.
    """

    emitted = (
        'def calculate(quantity: int, price: int) -> int:\n'
        '    _elmos_in_range(quantity)\n'
        '    _elmos_in_range(price)\n'
        '    """doc"""\n'
        '    return _elmos_checked_mul(quantity, price)\n'
    )
    with pytest.raises(RouteError) as raised:
        analyze_python(_write(tmp_path, emitted), "calculate", emitted_target=True)
    assert "PYTHON_UNSUPPORTED_STATEMENT" in str(raised.value)


def test_documentation_is_rejected_when_it_is_not_a_string(tmp_path: Path) -> None:
    """The IR contract stays exact; the new key is optional, not untyped."""

    mapping = analyze_python(_write(tmp_path, _DOCUMENTED), "calculate").to_mapping()
    mapping["functions"][0]["documentation"] = 17
    with pytest.raises(RouteError):
        SemanticIR.from_mapping(mapping)
