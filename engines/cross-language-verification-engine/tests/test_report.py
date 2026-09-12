from elmos_cross_language_verification.report import ReportGenerator
from elmos_cross_language_verification.models import VerificationReport

def test_generate_summary():
    report = VerificationReport(
        suite_id="s1",
        total=10,
        passed=8,
        failed=2,
        skipped=0,
        results=[],
        summary="",
        timestamp=0.0
    )
    summary = ReportGenerator.generate_summary(report)
    assert "8 passed" in summary
    assert "2 failed" in summary
