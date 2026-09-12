import unittest
from unittest.mock import patch, MagicMock

from elmos_cli.otel_collector import OtelCollectorService, get_otel_collector, OtelSpan

class TestOtelCollector(unittest.TestCase):
    def setUp(self):
        self.collector = OtelCollectorService()

    def test_init_default_trace(self):
        self.assertGreater(len(self.collector._spans), 0)
        self.assertEqual(self.collector._spans[0].name, "elmos.pipeline.cst_parsing")

    def test_record_span(self):
        span = self.collector.record_span(
            name="test.span",
            duration_ms=10.0,
            attributes={"key": "value"}
        )
        self.assertEqual(span.name, "test.span")
        self.assertEqual(span.duration_ms, 10.0)
        self.assertEqual(span.attributes["key"], "value")
        self.assertIn(span, self.collector._spans)

    def test_record_span_defaults(self):
        span = self.collector.record_span(
            name="test.span2",
            duration_ms=5.0
        )
        self.assertEqual(span.attributes, {})
        self.assertIsNotNone(span.trace_id)

    def test_export_otlp_json_all(self):
        self.collector.record_span("test", 1.0)
        out = self.collector.export_otlp_json()
        self.assertIn("resourceSpans", out)
        scopes = out["resourceSpans"][0]["scopeSpans"]
        self.assertGreater(len(scopes[0]["spans"]), 1)

    def test_export_otlp_json_filtered(self):
        span = self.collector.record_span("test", 1.0)
        out = self.collector.export_otlp_json(trace_id=span.trace_id)
        scopes = out["resourceSpans"][0]["scopeSpans"]
        self.assertEqual(len(scopes[0]["spans"]), 1)
        self.assertEqual(scopes[0]["spans"][0]["trace_id"], span.trace_id)

    def test_export_prometheus_text(self):
        out = self.collector.export_prometheus_text()
        self.assertIn("elmos_transformations_total", out)
        self.assertIn("elmos_cas_hit_ratio", out)
        self.assertIn("TYPE", out)
        self.assertIn("HELP", out)

    def test_get_otel_collector(self):
        col1 = get_otel_collector()
        col2 = get_otel_collector()
        self.assertIsInstance(col1, OtelCollectorService)
        self.assertIs(col1, col2)
