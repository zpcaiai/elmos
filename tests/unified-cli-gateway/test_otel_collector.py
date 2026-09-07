"""Unit tests for OpenTelemetry collector and Prometheus exporter."""

import io
import json
import sys
import unittest

from elmos_cli.dispatcher import main
from elmos_cli.otel_collector import OtelCollectorService, get_otel_collector


class OtelCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = OtelCollectorService()

    def test_record_span_and_export_otlp(self) -> None:
        span = self.collector.record_span(
            name="elmos.custom.test_stage",
            duration_ms=15.4,
            attributes={"test.key": "val"},
        )
        self.assertEqual(span.name, "elmos.custom.test_stage")
        self.assertEqual(span.duration_ms, 15.4)

        otlp = self.collector.export_otlp_json()
        self.assertIn("resourceSpans", otlp)
        spans = otlp["resourceSpans"][0]["scopeSpans"][0]["spans"]
        self.assertTrue(any(s["name"] == "elmos.custom.test_stage" for s in spans))

    def test_prometheus_exposition(self) -> None:
        metrics_text = self.collector.export_prometheus_text()
        self.assertIn("elmos_transformations_total", metrics_text)
        self.assertIn("elmos_cas_hit_ratio", metrics_text)

    def test_cli_telemetry_export_otlp(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["telemetry", "export-otlp", "--json"])
            self.assertEqual(code, 0)
            data = json.loads(sys.stdout.getvalue())
            self.assertIn("resourceSpans", data)
        finally:
            sys.stdout = stdout_orig

    def test_cli_telemetry_metrics(self) -> None:
        stdout_orig = sys.stdout
        sys.stdout = io.StringIO()
        try:
            code = main(["telemetry", "metrics"])
            self.assertEqual(code, 0)
            text = sys.stdout.getvalue()
            self.assertIn("elmos_ast_nodes_parsed_total", text)
        finally:
            sys.stdout = stdout_orig


if __name__ == "__main__":
    unittest.main()
