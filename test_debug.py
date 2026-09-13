import sys
from pathlib import Path
SRC = Path("engines/mature-platform-engine/src").resolve()
sys.path.insert(0, str(SRC))
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
slo_pipeline = EnterpriseSloCollector()
for _ in range(50):
    slo_pipeline.record_sample("http_request_duration_ms", 150.0)
res = slo_pipeline.evaluate_slo("api-p99-latency")
print("Compliant?", res.is_compliant, "Actual Pct:", res.actual_percentage, "Total 1h:", len([s for s in slo_pipeline.samples["http_request_duration_ms"] if s.timestamp >= __import__('time').time() - 3600]))
print("Alerts:", slo_pipeline.active_alerts)
