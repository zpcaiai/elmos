from elmos_assurance.sql_examples import not_in_vs_not_exists

def test_inner_nonnull_alone_does_not_justify_rewrite():
    original, rewritten = not_in_vs_not_exists([None, 1, 2], [1])
    assert original == [(2,)]
    assert rewritten == [(None,), (2,)]

def test_inner_null_is_a_separate_counterexample():
    original, rewritten = not_in_vs_not_exists([1, 2], [1, None])
    assert original == []
    assert rewritten == [(2,)]

def test_empty_subquery_boundary_is_not_blanket_nonnull_filter():
    original, rewritten = not_in_vs_not_exists([None, 2], [])
    assert original == rewritten == [(None,), (2,)]

def test_nonnull_values_keep_duplicate_multiplicity():
    original, rewritten = not_in_vs_not_exists([1, 2, 2, 3], [1, 1, 3])
    assert original == rewritten == [(2,), (2,)]
