from __future__ import annotations

import json
from dataclasses import asdict
from .models import VerificationReport, ComparisonResult

class ReportGenerator:
    @classmethod
    def generate_summary(cls, report: VerificationReport) -> str:
        return f"Verification Summary: {report.passed} passed, {report.failed} failed out of {report.total} tests."

    @classmethod
    def generate_json_report(cls, report: VerificationReport) -> str:
        return json.dumps(asdict(report), indent=2)

    @classmethod
    def generate_html_report(cls, report: VerificationReport) -> str:
        html = f"<html><body><h1>Verification Report</h1><p>{cls.generate_summary(report)}</p></body></html>"
        return html

    @classmethod
    def generate_diff_detail(cls, comparison: ComparisonResult) -> str:
        if comparison.match:
            return "No differences."
        return f"Diff: {comparison.diff_summary}"
