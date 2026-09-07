from etgb.coverage import coverage_report
from etgb.io import package_root


def test_declared_matrix_is_complete() -> None:
    report = coverage_report(package_root())
    assert report["complete"] is True, report
    assert report["missing_case_count"] == 0
