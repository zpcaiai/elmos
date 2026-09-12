import unittest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from elmos_mature_platform.types import (
    TelemetryMetricType,
    TelemetryAnomalySeverity,
    TelemetryDataPoint,
    TelemetryAnomalyAlert,
    ObservabilityExportReport
)
from elmos_mature_platform.global_observability_telemetry_engine import GlobalObservabilityTelemetryEngine

class TestGlobalObservabilityTelemetryEngine(unittest.TestCase):
    def setUp(self):
        self.engine = GlobalObservabilityTelemetryEngine()

    def test_ingest_single_datapoint_generates_timestamp(self):
        point = TelemetryDataPoint(
            point_id="p1",
            metric_name="cpu_usage",
            metric_type=TelemetryMetricType.GAUGE,
            value=45.0,
            region="us-east-1",
            service="backend"
        )
        self.engine.ingest_datapoint(point)
        self.assertEqual(len(self.engine._data_points), 1)
        self.assertTrue(point.timestamp != "")

    def test_ingest_single_datapoint_preserves_timestamp(self):
        ts = "2023-01-01T00:00:00Z"
        point = TelemetryDataPoint(
            point_id="p2",
            metric_name="memory_usage",
            metric_type=TelemetryMetricType.GAUGE,
            value=80.0,
            timestamp=ts
        )
        self.engine.ingest_datapoint(point)
        self.assertEqual(self.engine._data_points[0].timestamp, ts)

    def test_ingest_batch(self):
        points = [
            TelemetryDataPoint(point_id=f"p{i}", metric_name="test", metric_type=TelemetryMetricType.COUNTER, value=1.0)
            for i in range(5)
        ]
        count = self.engine.ingest_batch(points)
        self.assertEqual(count, 5)
        self.assertEqual(len(self.engine._data_points), 5)

    def test_set_metric_baseline(self):
        self.engine.set_metric_baseline("cpu_usage", 50.0, "us-east-1")
        self.assertEqual(self.engine._baselines[("cpu_usage", "us-east-1")], 50.0)
        # Default global
        self.engine.set_metric_baseline("mem_usage", 100.0)
        self.assertEqual(self.engine._baselines[("mem_usage", "global")], 100.0)

    def test_detect_anomalies_no_baseline(self):
        point = TelemetryDataPoint(point_id="p1", metric_name="cpu_usage", metric_type=TelemetryMetricType.GAUGE, value=100.0)
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("cpu_usage")
        self.assertEqual(len(alerts), 0)

    def test_detect_anomalies_below_threshold(self):
        self.engine.set_metric_baseline("cpu_usage", 50.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="cpu_usage", metric_type=TelemetryMetricType.GAUGE, value=55.0) # 10% deviation
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("cpu_usage", 20.0)
        self.assertEqual(len(alerts), 0)

    def test_detect_anomalies_minor(self):
        self.engine.set_metric_baseline("cpu_usage", 50.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="cpu_usage", metric_type=TelemetryMetricType.GAUGE, value=65.0) # 30% deviation
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("cpu_usage", 20.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.MINOR)

    def test_detect_anomalies_major(self):
        self.engine.set_metric_baseline("cpu_usage", 50.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="cpu_usage", metric_type=TelemetryMetricType.GAUGE, value=80.0) # 60% deviation
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("cpu_usage", 20.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.MAJOR)

    def test_detect_anomalies_critical(self):
        self.engine.set_metric_baseline("cpu_usage", 50.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="cpu_usage", metric_type=TelemetryMetricType.GAUGE, value=110.0) # 120% deviation
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("cpu_usage", 20.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.CRITICAL)

    def test_detect_anomalies_zero_baseline(self):
        self.engine.set_metric_baseline("errors", 0.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="errors", metric_type=TelemetryMetricType.COUNTER, value=5.0)
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("errors", 20.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.CRITICAL)

    def test_detect_anomalies_zero_baseline_zero_val(self):
        self.engine.set_metric_baseline("errors", 0.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="errors", metric_type=TelemetryMetricType.COUNTER, value=0.0)
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("errors", 20.0)
        self.assertEqual(len(alerts), 0)

    def test_acknowledge_alert_success(self):
        self.engine.set_metric_baseline("cpu_usage", 50.0)
        point = TelemetryDataPoint(point_id="p1", metric_name="cpu_usage", metric_type=TelemetryMetricType.GAUGE, value=110.0)
        self.engine.ingest_datapoint(point)
        alerts = self.engine.detect_anomalies("cpu_usage", 20.0)
        alert_id = alerts[0].alert_id
        
        updated_alert = self.engine.acknowledge_alert(alert_id, "Investigated, normal spike")
        self.assertTrue(updated_alert.acknowledged)
        self.assertEqual(updated_alert.resolution_notes, "Investigated, normal spike")
        self.assertTrue(self.engine._alerts[alert_id].acknowledged)

    def test_acknowledge_alert_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.acknowledge_alert("non-existent", "notes")

    def test_query_metric_aggregate_empty(self):
        res = self.engine.query_metric_aggregate("non_existent")
        self.assertEqual(res["count"], 0)
        self.assertEqual(res["avg"], 0.0)

    def test_query_metric_aggregate_all(self):
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="latency", metric_type=TelemetryMetricType.GAUGE, value=10.0),
            TelemetryDataPoint(point_id="2", metric_name="latency", metric_type=TelemetryMetricType.GAUGE, value=20.0),
            TelemetryDataPoint(point_id="3", metric_name="latency", metric_type=TelemetryMetricType.GAUGE, value=30.0)
        ])
        res = self.engine.query_metric_aggregate("latency")
        self.assertEqual(res["count"], 3)
        self.assertEqual(res["min"], 10.0)
        self.assertEqual(res["max"], 30.0)
        self.assertEqual(res["sum"], 60.0)
        self.assertEqual(res["avg"], 20.0)

    def test_query_metric_aggregate_with_filters(self):
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="req", metric_type=TelemetryMetricType.COUNTER, value=5.0, region="r1", service="s1"),
            TelemetryDataPoint(point_id="2", metric_name="req", metric_type=TelemetryMetricType.COUNTER, value=10.0, region="r2", service="s1"),
            TelemetryDataPoint(point_id="3", metric_name="req", metric_type=TelemetryMetricType.COUNTER, value=15.0, region="r1", service="s2"),
            TelemetryDataPoint(point_id="4", metric_name="req", metric_type=TelemetryMetricType.COUNTER, value=20.0, region="r1", service="s1")
        ])
        res1 = self.engine.query_metric_aggregate("req", region="r1")
        self.assertEqual(res1["count"], 3)
        
        res2 = self.engine.query_metric_aggregate("req", service="s1")
        self.assertEqual(res2["count"], 3)
        
        res3 = self.engine.query_metric_aggregate("req", region="r1", service="s1")
        self.assertEqual(res3["count"], 2)
        self.assertEqual(res3["sum"], 25.0)

    def test_detect_cost_anomalies_no_match(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=100.0, service="s1"
        ))
        alerts = self.engine.detect_cost_anomalies("s1", 10.0)
        self.assertEqual(len(alerts), 0)

    def test_detect_cost_anomalies_match_metric_name_no_anomaly(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="db_cost_usd", metric_type=TelemetryMetricType.GAUGE, value=12.0, service="db"
        ))
        alerts = self.engine.detect_cost_anomalies("db", 10.0, surge_multiplier=1.5)
        self.assertEqual(len(alerts), 0)

    def test_detect_cost_anomalies_match_metric_name_anomaly(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="db_cost_usd", metric_type=TelemetryMetricType.GAUGE, value=25.0, service="db"
        ))
        alerts = self.engine.detect_cost_anomalies("db", 10.0, surge_multiplier=1.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.CRITICAL)

    def test_detect_cost_anomalies_match_tag_anomaly(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="reqs", metric_type=TelemetryMetricType.COUNTER, value=100.0, service="api",
            tags={"cost_per_hour": "18.0"}
        ))
        alerts = self.engine.detect_cost_anomalies("api", 10.0, surge_multiplier=1.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].observed_value, 18.0)
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.MAJOR)

    def test_detect_cost_anomalies_service_mismatch(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="db_cost_usd", metric_type=TelemetryMetricType.GAUGE, value=25.0, service="other"
        ))
        alerts = self.engine.detect_cost_anomalies("db", 10.0)
        self.assertEqual(len(alerts), 0)

    def test_export_evidence_report(self):
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=1.0, region="r1", service="s1"),
            TelemetryDataPoint(point_id="2", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=1.0, region="r2", service="s2"),
            TelemetryDataPoint(point_id="3", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=1.0, region="r1", service="s3")
        ])
        
        # trigger an alert
        self.engine.set_metric_baseline("m1", 0.1, "r1")
        self.engine.detect_anomalies("m1")
        
        report = self.engine.export_evidence_report(time_window_hours=12)
        self.assertEqual(report.time_window_hours, 12)
        self.assertEqual(report.total_datapoints, 3)
        self.assertTrue(report.anomalies_detected > 0)
        self.assertEqual(set(report.services_monitored), {"s1", "s2", "s3"})
        self.assertEqual(report.regional_breakdown, {"r1": 2, "r2": 1})

    def test_get_telemetry_summary(self):
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=1.0, service="s1"),
            TelemetryDataPoint(point_id="2", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=1.0, service="s2")
        ])
        
        self.engine.set_metric_baseline("m1", 0.1)
        alerts = self.engine.detect_anomalies("m1")
        self.engine.acknowledge_alert(alerts[0].alert_id, "ack")
        
        summary = self.engine.get_telemetry_summary()
        self.assertEqual(summary["total_points"], 2)
        self.assertEqual(summary["total_alerts"], 2)
        self.assertEqual(summary["unacknowledged_alerts"], 1)
        self.assertEqual(summary["monitored_services"], 2)

    def test_purge_old_datapoints(self):
        ts_old1 = "2023-01-01T10:00:00Z"
        ts_old2 = "2023-01-01T11:00:00Z"
        ts_new = "2023-01-01T12:00:00Z"
        
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="m", metric_type=TelemetryMetricType.GAUGE, value=1.0, timestamp=ts_old1),
            TelemetryDataPoint(point_id="2", metric_name="m", metric_type=TelemetryMetricType.GAUGE, value=1.0, timestamp=ts_old2),
            TelemetryDataPoint(point_id="3", metric_name="m", metric_type=TelemetryMetricType.GAUGE, value=1.0, timestamp=ts_new)
        ])
        
        purged = self.engine.purge_old_datapoints("2023-01-01T11:30:00Z")
        self.assertEqual(purged, 2)
        self.assertEqual(len(self.engine._data_points), 1)
        self.assertEqual(self.engine._data_points[0].timestamp, ts_new)

    def test_detect_anomalies_multiple_regions(self):
        self.engine.set_metric_baseline("cpu", 50.0, "us-east-1")
        self.engine.set_metric_baseline("cpu", 60.0, "us-west-1")
        
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=100.0, region="us-east-1"),
            TelemetryDataPoint(point_id="2", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=70.0, region="us-west-1") # < 20% deviation
        ])
        
        alerts = self.engine.detect_anomalies("cpu", 20.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].region, "us-east-1")

    def test_detect_cost_anomalies_tag_invalid_float(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="reqs", metric_type=TelemetryMetricType.COUNTER, value=50.0, service="api",
            tags={"cost_per_hour": "invalid"}
        ))
        # It should fall back to checking value = 50.0
        alerts = self.engine.detect_cost_anomalies("api", 10.0, surge_multiplier=1.5)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].observed_value, 50.0)

    def test_query_metric_aggregate_only_service(self):
        self.engine.ingest_batch([
            TelemetryDataPoint(point_id="1", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=10.0, region="r1", service="s1"),
            TelemetryDataPoint(point_id="2", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=20.0, region="r2", service="s1"),
            TelemetryDataPoint(point_id="3", metric_name="m1", metric_type=TelemetryMetricType.GAUGE, value=30.0, region="r1", service="s2")
        ])
        res = self.engine.query_metric_aggregate("m1", service="s1")
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["sum"], 30.0)

    def test_purge_old_datapoints_no_match(self):
        ts_new = "2023-01-01T12:00:00Z"
        self.engine.ingest_datapoint(
            TelemetryDataPoint(point_id="3", metric_name="m", metric_type=TelemetryMetricType.GAUGE, value=1.0, timestamp=ts_new)
        )
        purged = self.engine.purge_old_datapoints("2023-01-01T11:30:00Z")
        self.assertEqual(purged, 0)
        self.assertEqual(len(self.engine._data_points), 1)

    def test_purge_old_datapoints_all_match(self):
        ts_old = "2023-01-01T10:00:00Z"
        self.engine.ingest_datapoint(
            TelemetryDataPoint(point_id="3", metric_name="m", metric_type=TelemetryMetricType.GAUGE, value=1.0, timestamp=ts_old)
        )
        purged = self.engine.purge_old_datapoints("2023-01-01T11:30:00Z")
        self.assertEqual(purged, 1)
        self.assertEqual(len(self.engine._data_points), 0)

    def test_export_evidence_report_no_data(self):
        report = self.engine.export_evidence_report()
        self.assertEqual(report.total_datapoints, 0)
        self.assertEqual(report.anomalies_detected, 0)
        self.assertEqual(report.services_monitored, [])
        self.assertEqual(report.regional_breakdown, {})

    def test_get_telemetry_summary_no_data(self):
        summary = self.engine.get_telemetry_summary()
        self.assertEqual(summary["total_points"], 0)
        self.assertEqual(summary["total_alerts"], 0)
        self.assertEqual(summary["unacknowledged_alerts"], 0)
        self.assertEqual(summary["monitored_services"], 0)

    def test_detect_anomalies_multiple_times(self):
        self.engine.set_metric_baseline("cpu", 50.0)
        self.engine.ingest_datapoint(TelemetryDataPoint(point_id="p1", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=100.0))
        alerts1 = self.engine.detect_anomalies("cpu")
        self.assertEqual(len(alerts1), 1)
        alerts2 = self.engine.detect_anomalies("cpu")
        self.assertEqual(len(alerts2), 1)
        self.assertEqual(len(self.engine._alerts), 2)  # Should generate a new alert

    def test_anomaly_severity_boundaries(self):
        self.engine.set_metric_baseline("cpu", 100.0)
        # Minor > 20%
        self.engine.ingest_datapoint(TelemetryDataPoint(point_id="p1", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=121.0))
        # Major > 50%
        self.engine.ingest_datapoint(TelemetryDataPoint(point_id="p2", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=151.0))
        # Critical > 100%
        self.engine.ingest_datapoint(TelemetryDataPoint(point_id="p3", metric_name="cpu", metric_type=TelemetryMetricType.GAUGE, value=201.0))
        
        alerts = self.engine.detect_anomalies("cpu")
        self.assertEqual(len(alerts), 3)
        severities = [a.severity for a in alerts]
        self.assertIn(TelemetryAnomalySeverity.MINOR, severities)
        self.assertIn(TelemetryAnomalySeverity.MAJOR, severities)
        self.assertIn(TelemetryAnomalySeverity.CRITICAL, severities)

    def test_detect_cost_anomalies_zero_expected(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="db_cost_usd", metric_type=TelemetryMetricType.GAUGE, value=25.0, service="db"
        ))
        alerts = self.engine.detect_cost_anomalies("db", 0.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].deviation_pct, float('inf'))
        self.assertEqual(alerts[0].severity, TelemetryAnomalySeverity.CRITICAL)

    def test_detect_cost_anomalies_no_tags_no_cost_in_name(self):
        self.engine.ingest_datapoint(TelemetryDataPoint(
            point_id="1", metric_name="reqs", metric_type=TelemetryMetricType.COUNTER, value=25.0, service="db"
        ))
        alerts = self.engine.detect_cost_anomalies("db", 10.0)
        self.assertEqual(len(alerts), 0)

if __name__ == '__main__':
    unittest.main()
