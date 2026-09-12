from elmos_cross_language_verification.uir_default_interface_methods import DefaultMethodResolver, TargetLanguageStrategy

def test_resolve_python():
    resolver = DefaultMethodResolver()
    res = resolver.resolve("MyInterface", ["doSomething"], "python")
    assert res.strategy == TargetLanguageStrategy.ABC_MIXIN

def test_resolve_go():
    resolver = DefaultMethodResolver()
    res = resolver.resolve("MyInterface", ["doSomething"], "go")
    assert res.strategy == TargetLanguageStrategy.EMBEDDED_STRUCT

def test_resolve_too_many():
    resolver = DefaultMethodResolver()
    try:
        resolver.resolve("MyInterface", ["doSomething"] * 101, "python")
        assert False
    except ValueError:
        assert True
