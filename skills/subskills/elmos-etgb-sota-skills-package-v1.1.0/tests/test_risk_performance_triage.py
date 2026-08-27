from etgb.performance import evaluate_performance, large_repository_tier
from etgb.risk import select_risk_plan
from etgb.triage import cluster_failures


def case(case_id: str, line: str, priority: str, profile: str = "pr") -> dict:
    return {"id": case_id, "business_line": line, "priority": priority, "level": "L2",
            "profiles": [profile], "family": "transaction" if case_id == "a" else "other",
            "coverage": {"capability_id": "cap-" + case_id}, "tags": []}


def test_risk_selection_is_deterministic_and_keeps_affected_p0() -> None:
    cases = [case("a", "spring-modernization", "P0"), case("b", "sql-conversion", "P2"),
             case("c", "cross-language", "P1")]
    p1 = select_risk_plan(cases, affected_lines={"spring-modernization"}, max_cases=2, seed=7)
    p2 = select_risk_plan(cases, affected_lines={"spring-modernization"}, max_cases=2, seed=7)
    assert p1["plan_digest"] == p2["plan_digest"]
    assert "a" in p1["case_ids"]


def test_performance_and_large_repo_tier() -> None:
    report = evaluate_performance(
        {"latency_p95_ms": 120, "throughput_per_second": 90},
        {"latency_p95_ms": {"direction": "max", "limit": 100},
         "throughput_per_second": {"direction": "min", "limit": 80}},
    )
    assert not report["passed"]
    assert large_repository_tier(1_000_000, 20, 5) == "L4-mega"


def test_failure_triage_clusters_equivalent_failures() -> None:
    rows = [
        {"case_id": "c", "business_line": "sql-conversion", "status": "failed",
         "oracle_results": [{"type": "transaction", "message": "rollback mismatch row 10"}]},
        {"case_id": "c", "business_line": "sql-conversion", "status": "failed",
         "oracle_results": [{"type": "transaction", "message": "rollback mismatch row 99"}]},
    ]
    report = cluster_failures(rows)
    assert report["cluster_count"] == 1
    assert report["clusters"][0]["failure_class"] == "state-transaction-mismatch"
