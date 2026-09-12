import sys
from pathlib import Path
SRC = Path("engines/mature-platform-engine/src").resolve()
sys.path.insert(0, str(SRC))
from elmos_mature_platform.slo_telemetry_pipeline import EnterpriseSloCollector
slo_pipeline = EnterpriseSloCollector()
for _ in range(50):
    slo_pipeline.record_sample("http_request_duration_ms", 150.0)
slo = slo_pipeline.slos["api-p99-latency"]
print("Metric:", slo.metric_name)
print("Threshold:", slo.threshold_value)
samples = slo_pipeline.samples["http_request_duration_ms"]
print("Samples count:", len(samples))
if samples:
    print("Sample 0 value:", samples[0].value)
    print("Is <= threshold?", samples[0].value <= slo.threshold_value)
    print("ratio in metric name?", "ratio" in slo.metric_name)

