from elmos_cross_language_verification.comparator import OutputComparator

def test_compare_json_match():
    match, diffs = OutputComparator.compare_json({"a": 1}, {"a": 1})
    assert match is True
    assert len(diffs) == 0

def test_compare_json_mismatch():
    match, diffs = OutputComparator.compare_json({"a": 1}, {"a": 2})
    assert match is False
    assert len(diffs) > 0

def test_compare_text():
    assert OutputComparator.compare_text(" a  b ", "a b") is True
