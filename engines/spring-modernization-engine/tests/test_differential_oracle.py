import socket
import sys

import pytest

from elmos_spring_modernization.differential_oracle import (
    DifferentialOracle,
    ResponseComparator
)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_configure_starts_and_stops_real_runtimes(tmp_path):
    source_port = _free_port()
    target_port = _free_port()
    while target_port == source_port:
        target_port = _free_port()
    command = [sys.executable, "-m", "http.server", "{port}", "--bind", "127.0.0.1", "--directory", str(tmp_path)]
    oracle = DifferentialOracle()
    try:
        config = oracle.configure(
            [part.format(port=source_port) for part in command],
            [part.format(port=target_port) for part in command],
            source_port=source_port,
            target_port=target_port,
            startup_timeout_seconds=5,
        )
        assert config.source_base_url == f"http://127.0.0.1:{source_port}"
        assert config.target_base_url == f"http://127.0.0.1:{target_port}"
        report = oracle.run_tests([{"method": "GET", "path": "/"}])
        assert report.passed == 1
        assert report.failed == 0
    finally:
        oracle.manager.stop_runtimes()


def test_configure_fails_closed_when_runtime_cannot_start():
    oracle = DifferentialOracle()
    source_port = _free_port()
    target_port = _free_port()
    while target_port == source_port:
        target_port = _free_port()
    with pytest.raises(RuntimeError, match="runtime launch failed"):
        oracle.configure(
            ["definitely-not-an-elmos-executable"],
            ["also-not-an-elmos-executable"],
            source_port=source_port,
            target_port=target_port,
            startup_timeout_seconds=0.2,
        )

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
