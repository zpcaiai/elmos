import math

import pytest

from elmos_execution_intelligence.io_utils import markdown_table, quantile, summarize


def test_quantile_matches_linear_interpolation():
    values = [1, 2, 3, 4]
    assert quantile(values, 0.0) == 1
    assert quantile(values, 1.0) == 4
    assert math.isclose(quantile(values, 0.5), 2.5)
    assert math.isclose(quantile(values, 0.8), 3.4)


def test_quantile_rejects_empty_and_out_of_range():
    with pytest.raises(ValueError):
        quantile([], 0.5)
    with pytest.raises(ValueError):
        quantile([1.0], 1.5)


def test_summarize_is_monotonic_across_the_envelope():
    values = list(range(1, 1001))
    result = summarize(values, worst_probability=0.99)
    assert (result["minimum"] <= result["p50"] <= result["p80"] <= result["p90"]
            <= result["worst_case"] <= result["maximum"])


def test_summarize_rejects_empty():
    with pytest.raises(ValueError):
        summarize([])


def test_markdown_table_renders_header_separator():
    table = markdown_table(["a", "b"], [[1, 2]])
    assert table.splitlines()[1] == "|---|---|"
