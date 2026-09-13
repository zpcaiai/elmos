from elmos_cross_language_verification.test_generator import TestCaseGenerator

def test_generate_from_function_signature():
    cases = TestCaseGenerator.generate_from_function_signature("foo", {"a": "int"}, "int", None)
    assert len(cases) > 0
    assert "a" in cases[0]

def test_generate_boundary_tests():
    cases = TestCaseGenerator.generate_boundary_tests("foo", {"b": "string"})
    assert len(cases) == 1
    assert cases[0]["b"] == ""
