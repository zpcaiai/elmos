from elmos_cross_language_verification.harness import HarnessGenerator

def test_generate_python_harness():
    code = HarnessGenerator.generate_python_harness({}, [])
    assert isinstance(code, str)
