import datetime as dt

from etgb.gates import evaluate_gates
from etgb.statistics import multi_seed_stability, non_inferiority, wilson_interval


def test_non_waivable_gate_rejects_and_waivable_gate_can_pass_with_waiver() -> None:
    gates = {"gates": [
        {"id": "G-P0-SSER", "metric": "sser", "operator": "==", "threshold": 0.0},
        {"id": "G-P2", "metric": "p2", "operator": ">=", "threshold": 0.95},
    ]}
    waiver = {"gate_ids": ["G-P0-SSER", "G-P2"], "approved_by": "qa-owner",
              "expires_at": (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=1)).isoformat()}
    report = evaluate_gates({"sser": 0.01, "p2": 0.90}, gates, waivers=[waiver])
    assert report["decision"] == "REJECT"
    assert {r["id"]: r["state"] for r in report["gate_results"]} == {"G-P0-SSER": "FAIL", "G-P2": "WAIVED"}


def test_statistics_detect_instability() -> None:
    low, high = wilson_interval(90, 100)
    assert 0 < low < 0.9 < high < 1
    assert non_inferiority(99, 100, 100, 100, margin=0.05)["non_inferior"]
    report = multi_seed_stability([
        {"case_id": "c", "seed": 1, "status": "passed", "duration_ms": 10},
        {"case_id": "c", "seed": 2, "status": "failed", "duration_ms": 20},
        {"case_id": "c", "seed": 3, "status": "passed", "duration_ms": 15},
    ])
    assert report["unstable_case_count"] == 1
    assert report["insufficient_seed_case_count"] == 0
