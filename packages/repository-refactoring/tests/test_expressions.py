"""The predicate language, with emphasis on its three-valued behaviour."""

from __future__ import annotations

import pytest

from elmos_repository_refactoring.contracts import ContractError
from elmos_repository_refactoring.expressions import UNKNOWN, compile_expression, evaluate_expression

CONTEXT = {
    "risk": {"class": "R4", "score": 0.8},
    "files": ["src/a.py", "src/b.ts"],
    "impact": {"database_touched": True, "public_api_touched": False},
    "count": 12,
    "name": "UserService",
    "nested": {"deep": {"value": [1, 2, 3]}},
}


class TestTruth:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("risk.class == 'R4'", True),
            ("risk.class != 'R4'", False),
            ("count > 10 and count < 20", True),
            ("count >= 12 and count <= 12", True),
            ("not impact.public_api_touched", True),
            ("'src/a.py' in files", True),
            ("files contains 'src/b.ts'", True),
            ("len(files) == 2", True),
            ("name startswith 'User'", True),
            ("name endswith 'Service'", True),
            ("'src/x/y.py' matches 'src/**/*.py'", True),
            ("glob('src/x/y.py', 'src/**/*.ts')", False),
            ("nested.deep.value[1] == 2", True),
            ("risk.score > 0.5", True),
            ("count in [1, 12]", True),
            ("count not in [1, 2]", True),
            ("(count > 100 or risk.class == 'R4') and impact.database_touched", True),
        ],
    )
    def test_decidable_expressions(self, source: str, expected: bool) -> None:
        assert evaluate_expression(source, CONTEXT) is expected


class TestUnknown:
    def test_missing_path_is_unknown_not_false(self) -> None:
        assert evaluate_expression("missing.thing == 1", CONTEXT) is UNKNOWN

    def test_unknown_and_false_is_false(self) -> None:
        assert evaluate_expression("missing.thing == 1 and count > 100", CONTEXT) is False

    def test_unknown_or_true_is_true(self) -> None:
        assert evaluate_expression("missing.thing == 1 or count > 10", CONTEXT) is True

    def test_unknown_and_true_stays_unknown(self) -> None:
        assert evaluate_expression("missing.thing == 1 and count > 10", CONTEXT) is UNKNOWN

    def test_not_unknown_is_unknown(self) -> None:
        assert evaluate_expression("not missing.thing", CONTEXT) is UNKNOWN

    def test_defined_distinguishes_absent_from_null(self) -> None:
        assert evaluate_expression("defined(missing.thing)", CONTEXT) is False
        assert evaluate_expression("defined(count)", CONTEXT) is True

    def test_indexing_past_the_end_is_unknown(self) -> None:
        assert evaluate_expression("nested.deep.value[99] == 1", CONTEXT) is UNKNOWN

    def test_unknown_has_no_boolean_value(self) -> None:
        with pytest.raises(ContractError):
            bool(UNKNOWN)


class TestSafety:
    @pytest.mark.parametrize(
        "source",
        [
            "1 +",
            "foo(",
            "a == 'b",
            "count > ",
            "",
            "   ",
            "__import__('os')",
            "count.__class__",
        ],
    )
    def test_malformed_or_dangerous_input_is_refused_or_unknown(self, source: str) -> None:
        try:
            result = evaluate_expression(source, CONTEXT)
        except ContractError:
            return
        assert result in (True, False) or result is UNKNOWN

    def test_no_attribute_escape_into_python_objects(self) -> None:
        # `__class__` is just a mapping key that does not exist.
        assert evaluate_expression("count.__class__ == 'int'", CONTEXT) is UNKNOWN

    def test_unknown_function_is_refused(self) -> None:
        with pytest.raises(ContractError) as error:
            evaluate_expression("system('rm -rf /')", CONTEXT)
        assert error.value.code == "unknown_function"

    def test_deeply_nested_expression_is_bounded(self) -> None:
        with pytest.raises(ContractError) as error:
            evaluate_expression("(" * 40 + "1" + ")" * 40, CONTEXT)
        assert error.value.code in ("expression_too_deep", "invalid_expression")

    def test_oversized_expression_is_refused(self) -> None:
        with pytest.raises(ContractError) as error:
            evaluate_expression("a == 'x' and " * 1000 + "b == 'y'", CONTEXT)
        assert error.value.code == "expression_too_long"


def test_referenced_paths_are_reported_for_coverage() -> None:
    expression = compile_expression("risk.class == 'R4' and impact.database_touched")
    assert expression.referenced_paths == ("impact.database_touched", "risk.class")


def test_compilation_is_memoised_but_stateless() -> None:
    first = compile_expression("count > 1")
    second = compile_expression("count > 1")
    assert first is second
    assert first.evaluate({"count": 5}) is True
    assert first.evaluate({"count": 0}) is False
