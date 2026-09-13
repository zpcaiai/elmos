from elmos_cross_language_verification.verification_service import VerificationService
from elmos_cross_language_verification.models import Language

def test_generate_and_verify():
    report = VerificationService.generate_and_verify(
        "def foo(a): return a",
        "int foo(int a) { return a; }",
        Language.PYTHON,
        Language.JAVA
    )
    assert report.total > 0
    assert report.passed == report.total
