from etgb.normalize import first_difference, normalize, remove_json_paths


def test_normalize_and_difference() -> None:
    left = normalize({"b": 1.0, "a": [1, 2]})
    right = normalize({"a": [1, 2], "b": 1.0})
    assert first_difference(left, right) is None
    assert first_difference(left, {"a": [1, 3], "b": 1.0})["path"] == "$.a[1]"


def test_remove_json_path() -> None:
    assert remove_json_paths({"a": {"b": 1}, "x": 2}, ["$.a.b"]) == {"a": {}, "x": 2}
