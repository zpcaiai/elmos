"""Tests for elmos_cli.formatters — properly mocking yaml."""

import sys
import json
from unittest.mock import MagicMock

# Mock yaml as a proper module-like object with a dump that serializes
_mock_yaml = MagicMock()
def _yaml_dump(data, **kwargs):
    """Simple yaml-like serializer using only stdlib."""
    if isinstance(data, dict):
        return "\n".join(f"{k}: {v}" for k, v in data.items()) + "\n"
    if isinstance(data, list):
        return "\n".join(f"- {item}" for item in data) + "\n"
    return str(data) + "\n"

_mock_yaml.dump = _yaml_dump
_mock_yaml.safe_load = lambda x: {}
sys.modules['yaml'] = _mock_yaml

import os
import tempfile
import unittest
from pathlib import Path
from elmos_cli.formatters import format_table, format_output, generate_executive_html_report


class TestFormatTable(unittest.TestCase):
    """Tests for format_table grid rendering."""

    def test_empty_rows(self):
        res = format_table(["A", "B"], [])
        self.assertEqual(res, "(empty table)")

    def test_basic_data(self):
        res = format_table(["A", "B"], [[1, 2], ["long string", 4]])
        self.assertIn("| A           | B |", res)
        self.assertIn("| 1           | 2 |", res)
        self.assertIn("| long string | 4 |", res)
        self.assertIn("+=============+===+", res)

    def test_single_column(self):
        res = format_table(["Name"], [["Alice"], ["Bob"]])
        self.assertIn("Name", res)
        self.assertIn("Alice", res)
        self.assertIn("Bob", res)

    def test_wide_cells(self):
        res = format_table(["X"], [["a" * 50]])
        self.assertIn("a" * 50, res)

    def test_empty_headers(self):
        res = format_table([], [[1, 2]])
        self.assertIsInstance(res, str)


class TestFormatOutput(unittest.TestCase):
    """Tests for format_output multi-format rendering."""

    def test_json_format(self):
        res = format_output({"a": 1}, "json")
        self.assertEqual(json.loads(res), {"a": 1})

    def test_json_unicode(self):
        res = format_output({"name": "名前"}, "json")
        self.assertIn("名前", res)

    def test_yaml_format_dict(self):
        res = format_output({"a": 1}, "yaml")
        self.assertIn("a:", res)

    def test_yaml_format_alias(self):
        res = format_output({"x": 2}, "yml")
        self.assertIn("x:", res)

    def test_markdown_dict(self):
        res = format_output({"a": "1", "b": [1, 2]}, "markdown")
        self.assertIn("| Key | Value |", res)
        self.assertIn("| :--- | :--- |", res)
        self.assertIn("| `a` | 1 |", res)

    def test_markdown_non_dict(self):
        res = format_output([1, 2], "markdown")
        self.assertIn("```yaml", res)

    def test_table_dict(self):
        res = format_output({"a": 1}, "table")
        self.assertIn("a:", res)

    def test_table_non_dict(self):
        res = format_output(123, "table")
        self.assertEqual(res, "123")

    def test_table_string(self):
        res = format_output("hello", "table")
        self.assertEqual(res, "hello")


class TestExecutiveReport(unittest.TestCase):
    """Tests for HTML report generation."""

    def test_basic_report(self):
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "report.html"
            payload = {
                "status": "SUCCESS",
                "total_duration_ms": 100,
                "stages": {
                    "stage1": {
                        "status": "SUCCESS",
                        "duration_ms": 10,
                        "sha256": "abcdef1234"
                    }
                }
            }
            generate_executive_html_report("Test Report", payload, out_file)
            self.assertTrue(out_file.is_file())
            content = out_file.read_text()
            self.assertIn("Test Report", content)
            self.assertIn("SUCCESS", content)
            self.assertIn("abcdef1234", content)
            self.assertIn("stage1", content)

    def test_report_empty_stages(self):
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "report2.html"
            payload = {"status": "PARTIAL", "stages": {}}
            generate_executive_html_report("Empty Stages", payload, out_file)
            self.assertTrue(out_file.is_file())
            content = out_file.read_text()
            self.assertIn("Empty Stages", content)
            self.assertIn("PARTIAL", content)

    def test_report_with_smt_finops(self):
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "report3.html"
            payload = {
                "status": "SUCCESS",
                "total_duration_ms": 500,
                "stages": {
                    "smt_formal_proof": {
                        "status": "SAT_PROVED",
                        "duration_ms": 200,
                        "sha256": "proof123"
                    },
                    "finops_metering": {
                        "status": "METERED",
                        "estimated_cost_usd": 0.05,
                        "duration_ms": 50,
                        "sha256": "cost456"
                    }
                }
            }
            generate_executive_html_report("Full Report", payload, out_file)
            self.assertTrue(out_file.is_file())
            content = out_file.read_text()
            self.assertIn("Full Report", content)
            self.assertIn("html", content.lower())

    def test_report_html_escape(self):
        """Title with HTML chars should be escaped."""
        with tempfile.TemporaryDirectory() as td:
            out_file = Path(td) / "report4.html"
            payload = {"status": "OK", "stages": {}}
            generate_executive_html_report("<script>alert(1)</script>", payload, out_file)
            self.assertTrue(out_file.is_file())
            content = out_file.read_text()
            self.assertNotIn("<script>alert(1)</script>", content)
            self.assertIn("&lt;script&gt;", content)
