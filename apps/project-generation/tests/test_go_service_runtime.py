"""Runtime integration tests verifying real execution, HTTP probes, and graceful shutdown of generated Go microservice."""

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from project_generation.engine import ProjectConfig, ProjectGenerator


def get_free_port() -> int:
    """Find an available port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp(prefix="test_go_runtime_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def test_go_microservice_live_execution_and_graceful_shutdown(temp_dir: Path):
    """End-to-end test: compile, run, probe live HTTP endpoints, verify RFC 7807, and test graceful SIGINT drain."""
    generator = ProjectGenerator()
    out_dir = temp_dir / "order-service"

    http_port = get_free_port()
    grpc_port = get_free_port()

    config = ProjectConfig(
        language="go",
        project_name="order-service",
        module_name="github.com/example/order-service",
        port=str(http_port),
        grpc_port=str(grpc_port),
        database="postgres",
        description="Live runtime tested order service",
        output_dir=str(out_dir),
    )

    result = generator.generate(config)
    assert result.success is True, f"Failed to generate Go project: {result.error}"

    # 1. Build the real executable binary
    binary_path = out_dir / "server"
    build_cmd = subprocess.run(
        ["go", "build", "-o", str(binary_path), "cmd/server/main.go"],
        cwd=str(out_dir),
        capture_output=True,
        text=True,
    )
    assert build_cmd.returncode == 0, f"go build failed:\n{build_cmd.stderr}\n{build_cmd.stdout}"
    assert binary_path.is_file(), "Executable binary was not created!"

    # 2. Launch the server process
    env = os.environ.copy()
    env["HTTP_PORT"] = str(http_port)
    env["GRPC_PORT"] = str(grpc_port)
    env["LOG_LEVEL"] = "info"
    env["LOG_FORMAT"] = "json"

    proc = subprocess.Popen(
        [str(binary_path)],
        cwd=str(out_dir),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    base_url = f"http://127.0.0.1:{http_port}"
    try:
        # 3. Poll /healthz until server is listening (up to 10 seconds)
        started = False
        start_deadline = time.time() + 10.0
        while time.time() < start_deadline:
            try:
                with urllib.request.urlopen(f"{base_url}/healthz", timeout=1.0) as resp:
                    if resp.status == 200:
                        started = True
                        break
            except Exception:
                time.sleep(0.1)

        assert started, "Go microservice failed to start and respond to /healthz within 10s!"

        # 4. Verify /livez and /readyz probes
        with urllib.request.urlopen(f"{base_url}/livez", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "alive"

        with urllib.request.urlopen(f"{base_url}/readyz", timeout=2.0) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data.get("status") == "ready"

        # 5. Verify Prometheus /metrics endpoint
        with urllib.request.urlopen(f"{base_url}/metrics", timeout=2.0) as resp:
            assert resp.status == 200
            metrics_text = resp.read().decode("utf-8")
            assert "http_requests_total" in metrics_text
            assert "service_up 1" in metrics_text

        # 6. Test Entity REST API: Create Entity (POST)
        create_payload = json.dumps({"name": "production-cluster", "description": "critical node"}).encode("utf-8")
        req = urllib.request.Request(
            f"{base_url}/api/v1/entities",
            data=create_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            assert resp.status == 201
            created_entity = json.loads(resp.read().decode("utf-8"))
            assert created_entity.get("name") == "production-cluster"
            entity_id = created_entity.get("id")
            assert entity_id

        # 7. Test Entity REST API: Get Entity (GET)
        with urllib.request.urlopen(f"{base_url}/api/v1/entities/{entity_id}", timeout=2.0) as resp:
            assert resp.status == 200
            fetched_entity = json.loads(resp.read().decode("utf-8"))
            assert fetched_entity.get("id") == entity_id
            assert fetched_entity.get("name") == "production-cluster"

        # 8. Test Entity REST API: List Entities (GET)
        with urllib.request.urlopen(f"{base_url}/api/v1/entities?limit=10", timeout=2.0) as resp:
            assert resp.status == 200
            list_res = json.loads(resp.read().decode("utf-8"))
            assert "items" in list_res
            assert any(item.get("id") == entity_id for item in list_res["items"])

        # 9. Test Error Handling & RFC 7807 Problem Details (POST malformed JSON)
        bad_req = urllib.request.Request(
            f"{base_url}/api/v1/entities",
            data=b"{invalid-json",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(bad_req, timeout=2.0)
            pytest.fail("Expected 400 Bad Request on malformed JSON payload")
        except urllib.error.HTTPError as err:
            assert err.code == 400
            content_type = err.headers.get("Content-Type", "")
            assert "application/problem+json" in content_type, f"Expected application/problem+json, got {content_type}"
            problem_body = json.loads(err.read().decode("utf-8"))
            assert problem_body.get("status") == 400
            assert problem_body.get("type") == "urn:problem-type:validation-error"

    finally:
        # 10. Send SIGINT and verify Graceful Drain & Exit 0
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            stdout, stderr = proc.communicate(timeout=10)
            assert proc.returncode == 0, f"Process exited with non-zero code {proc.returncode}"
            all_logs = stdout + stderr
            assert "Received shutdown signal, starting graceful drain" in all_logs
            assert "HTTP server drained and exited cleanly" in all_logs
            assert "Service graceful shutdown complete" in all_logs
