from elmos_cross_language_verification.uir_name_conflict_resolver import NameConflictResolver

def test_resolve_python():
    resolver = NameConflictResolver()
    res = resolver.resolve({"class", "def", "normal"}, "python")
    assert "class" in res.conflicts
    assert "def" in res.conflicts
    assert "normal" not in res.conflicts
    assert res.original_to_renamed["class"] == "class_"
    assert res.original_to_renamed["normal"] == "normal"

def test_resolve_go():
    resolver = NameConflictResolver()
    res = resolver.resolve({"type", "func", "normal"}, "go")
    assert "type" in res.conflicts
    assert res.original_to_renamed["type"] == "type_"

def test_resolve_too_many():
    resolver = NameConflictResolver()
    try:
        resolver.resolve({f"id{i}" for i in range(1001)}, "python")
        assert False
    except ValueError:
        assert True
