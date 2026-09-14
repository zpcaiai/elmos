import pytest
from elmos_spring_modernization.differential_oracle import (
    DifferentialOracle,
    ResponseComparator,
    HttpRequestReplayer
)

def test_configure():
    oracle = DifferentialOracle()
    config = oracle.configure("java -jar legacy.jar", "java -jar modern.jar", source_port=8080, target_port=9090)
    assert config.source_port == 8080
    assert config.target_port == 9090
    assert config.source_base_url == "http://localhost:8080"
    assert config.target_base_url == "http://localhost:9090"

def test_response_comparator_deep_json():
    comp = ResponseComparator()
    src = {
        "status": 200,
        "body": {"id": 101, "name": "Alice", "timestamp": "2026-09-01T12:00:00Z"}
    }
    tgt = {
        "status": 200,
        "body": {"id": 101, "name": "Alice", "timestamp": "2026-09-14T15:00:00Z"}
    }
    # Timestamps ignored by default
    assert comp.compare(src, tgt, ignore_timestamps=True) is True

    # Differences in non-volatile fields detected
    tgt_diff = {
        "status": 200,
        "body": {"id": 102, "name": "Alice", "timestamp": "2026-09-14T15:00:00Z"}
    }
    matches, diffs = comp.compare_detailed(src, tgt_diff, ignore_timestamps=True)
    assert matches is False
    assert any("id" in d for d in diffs)

def test_oracle_custom_executor():
    def mock_executor(role: str, req: dict) -> dict:
        if role == "source":
            return {"status": 200, "body": {"data": "legacy_val"}}
        else:
            return {"status": 200, "body": {"data": "modern_val" if req.get("diverge") else "legacy_val"}}

    oracle = DifferentialOracle(executor=mock_executor)
    report = oracle.run_tests([
        {"path": "/api/v1/same", "diverge": False},
        {"path": "/api/v1/diff", "diverge": True}
    ])

    assert report.total_requests == 2
    assert report.passed == 1
    assert report.differed == 1
    assert report.failed == 0
