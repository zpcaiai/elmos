from elmos_cross_language_verification.models import Language, TestCase, TestSuite

def test_language_enum():
    assert Language.JAVA.value == "java"
    assert Language.PYTHON.value == "python"

def test_test_case_creation():
    tc = TestCase(test_id="1", name="t1", input_data={"a": 1})
    assert tc.test_id == "1"
    assert tc.timeout_seconds == 30
