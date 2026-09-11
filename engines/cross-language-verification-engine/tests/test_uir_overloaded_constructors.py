from elmos_cross_language_verification.uir_overloaded_constructors import OverloadedConstructorResolver, ResolutionStrategy

def test_resolve_python():
    resolver = OverloadedConstructorResolver()
    res = resolver.resolve([["str"], ["str", "int"]], "python")
    assert res.strategy == ResolutionStrategy.FACTORY_METHODS

def test_resolve_go():
    resolver = OverloadedConstructorResolver()
    res = resolver.resolve([["str"], ["str", "int"]], "go")
    assert res.strategy == ResolutionStrategy.FUNCTIONAL_OPTIONS

def test_resolve_too_many():
    resolver = OverloadedConstructorResolver()
    try:
        resolver.resolve([["str"]] * 51, "python")
        assert False
    except ValueError:
        assert True
