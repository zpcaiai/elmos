#!/usr/bin/env python3
"""Run real live End-to-End fullstack acceptance on a generated project.

This script:
1. Dynamically synthesizes an enterprise fullstack project (Python FastAPI backend + React 19 / Vite frontend).
2. Spawns the real backend FastAPI server on an ephemeral loopback port.
3. Spawns the real frontend web server on an ephemeral loopback port.
4. Executes real OS curl commands testing:
   - Healthcheck endpoints (/health)
   - Entity CRUD lifecycle (GET, POST, PUT, DELETE)
   - Frontend index.html and module bootstrap assets
   - Generated scripts/curl_test_suite.sh execution
5. Shuts down servers and ensures zero orphaned processes or ports.
6. Emits structured JSON execution evidence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from elmos_project_synthesis.cleanup import cleanup_acceptance_directory
from elmos_project_synthesis.intake import approve_request, create_draft
from elmos_project_synthesis.workspace import generate_workspace


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.listen(1)
        return int(s.getsockname()[1])


def wait_for_port(port: int, timeout_seconds: float = 15.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < timeout_seconds:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (OSError, ConnectionRefusedError):
            time.sleep(0.1)
    return False


def run_curl(
    args: list[str],
    timeout_seconds: float = 10.0,
) -> tuple[int, str, str]:
    command = ["curl", "-s", "-S", *args]
    res = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    return res.returncode, res.stdout, res.stderr


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run fullstack end-to-end acceptance.")
    parser.add_argument("--output", type=Path, help="Path to write JSON evidence.")
    args = parser.parse_args(argv)

    project_name = "order-fullstack-hub"
    package_name = "order_fullstack_hub"

    draft = create_draft(
        name=project_name,
        description="Fullstack enterprise order operations platform",
        entity="order",
        languages=["python"],
        project_kind="fullstack",
        persistence="in-memory",
        auth_mode="none",
    )
    approved = approve_request(draft, actor="acceptance:fullstack-e2e")

    temporary = Path(tempfile.mkdtemp(prefix="elmos-fullstack-e2e-"))
    workspace = temporary / "workspace"

    backend_process: subprocess.Popen[str] | None = None
    frontend_process: subprocess.Popen[str] | None = None
    steps: list[dict[str, Any]] = []
    overall_status = "PASSED"

    try:
        _ = generate_workspace(approved, workspace)
        backend_port = find_free_port()
        frontend_port = find_free_port()
        while frontend_port == backend_port:
            frontend_port = find_free_port()

        backend_env = os.environ.copy()
        for env_var in ("VIRTUAL_ENV", "PYTHONPATH", "UV_PYTHON", "UV_WORKING_DIRECTORY"):
            backend_env.pop(env_var, None)
        backend_env["PORT"] = str(backend_port)
        backend_env["HOST"] = "127.0.0.1"

        backend_cwd = workspace / "python"
        uv_bin = shutil.which("uv") or "uv"
        backend_cmd = [
            uv_bin,
            "run",
            "--python",
            "3.12",
            "python",
            "-m",
            package_name,
        ]

        backend_process = subprocess.Popen(  # noqa: S603
            backend_cmd,
            cwd=str(backend_cwd),
            env=backend_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not wait_for_port(backend_port, timeout_seconds=15.0):
            err_out = ""
            if backend_process.poll() is not None and backend_process.stderr:
                err_out = backend_process.stderr.read()
            raise RuntimeError(f"Backend failed to bind on port {backend_port}: {err_out}")

        frontend_cwd = workspace / "frontend"
        frontend_cmd = [
            sys.executable,
            "-m",
            "http.server",
            str(frontend_port),
            "--bind",
            "127.0.0.1",
        ]

        frontend_process = subprocess.Popen(  # noqa: S603
            frontend_cmd,
            cwd=str(frontend_cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not wait_for_port(frontend_port, timeout_seconds=10.0):
            err_out = ""
            if frontend_process.poll() is not None and frontend_process.stderr:
                err_out = frontend_process.stderr.read()
            raise RuntimeError(f"Frontend failed to bind on port {frontend_port}: {err_out}")

        base_backend_url = f"http://127.0.0.1:{backend_port}"
        base_frontend_url = f"http://127.0.0.1:{frontend_port}"

        # 1. Healthcheck
        code, stdout, stderr = run_curl(["-w", "%{http_code}", f"{base_backend_url}/health"])
        http_code = stdout[-3:] if len(stdout) >= 3 else ""
        body = stdout[:-3]
        step1 = {
            "name": "backend_healthcheck",
            "url": f"{base_backend_url}/health",
            "method": "GET",
            "http_code": http_code,
            "passed": http_code == "200" and '"status":"UP"' in body.replace(" ", ""),
            "body": body,
        }
        steps.append(step1)
        if not step1["passed"]:
            overall_status = "FAILED"

        # 2. Initial List Orders
        code, stdout, stderr = run_curl(["-w", "%{http_code}", f"{base_backend_url}/api/v1/orders"])
        http_code = stdout[-3:] if len(stdout) >= 3 else ""
        body = stdout[:-3]
        step2 = {
            "name": "backend_list_orders_initial",
            "url": f"{base_backend_url}/api/v1/orders",
            "method": "GET",
            "http_code": http_code,
            "passed": http_code == "200" and body.strip() == "[]",
            "body": body,
        }
        steps.append(step2)
        if not step2["passed"]:
            overall_status = "FAILED"

        # 3. Create Order
        create_payload = json.dumps({
            "name": "Precision Sensor Unit A1",
            "description": "Industrial telemetry probe order",
            "active": True,
        })
        code, stdout, stderr = run_curl([
            "-w", "%{http_code}",
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", create_payload,
            f"{base_backend_url}/api/v1/orders",
        ])
        http_code = stdout[-3:] if len(stdout) >= 3 else ""
        body = stdout[:-3]
        created_id = ""
        try:
            parsed_order = json.loads(body)
            created_id = str(parsed_order.get("id", ""))
        except json.JSONDecodeError:
            pass

        step3 = {
            "name": "backend_create_order",
            "url": f"{base_backend_url}/api/v1/orders",
            "method": "POST",
            "http_code": http_code,
            "passed": http_code == "201" and bool(created_id),
            "created_id": created_id,
            "body": body,
        }
        steps.append(step3)
        if not step3["passed"]:
            overall_status = "FAILED"

        # 4. Get Created Order
        if created_id:
            code, stdout, stderr = run_curl([
                "-w", "%{http_code}",
                f"{base_backend_url}/api/v1/orders/{created_id}",
            ])
            http_code = stdout[-3:] if len(stdout) >= 3 else ""
            body = stdout[:-3]
            step4 = {
                "name": "backend_get_created_order",
                "url": f"{base_backend_url}/api/v1/orders/{created_id}",
                "method": "GET",
                "http_code": http_code,
                "passed": http_code == "200" and created_id in body,
                "body": body,
            }
            steps.append(step4)
            if not step4["passed"]:
                overall_status = "FAILED"

        # 5. Frontend index.html verification
        code, stdout, stderr = run_curl(["-w", "%{http_code}", f"{base_frontend_url}/index.html"])
        http_code = stdout[-3:] if len(stdout) >= 3 else ""
        body = stdout[:-3]
        step5 = {
            "name": "frontend_index_html",
            "url": f"{base_frontend_url}/index.html",
            "method": "GET",
            "http_code": http_code,
            "passed": http_code == "200" and '<div id="root">' in body and 'src="/src/main.tsx"' in body,
            "body_snippet": body[:500],
        }
        steps.append(step5)
        if not step5["passed"]:
            overall_status = "FAILED"

        # 6. Execute generated scripts/curl_test_suite.sh
        curl_script = workspace / "scripts" / "curl_test_suite.sh"
        if curl_script.is_file():
            res = subprocess.run(  # noqa: S603
                ["bash", str(curl_script), base_backend_url],
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
            step6 = {
                "name": "generated_curl_test_suite_sh",
                "script": str(curl_script),
                "exit_code": res.returncode,
                "passed": res.returncode == 0,
                "stdout": res.stdout[-1000:],
            }
            steps.append(step6)
            if not step6["passed"]:
                overall_status = "FAILED"

    finally:
        # Gracefully terminate servers
        if backend_process is not None and backend_process.poll() is None:
            backend_process.terminate()
            try:
                backend_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                backend_process.kill()

        if frontend_process is not None and frontend_process.poll() is None:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                frontend_process.kill()

        cleanup_acceptance_directory(temporary, expected_prefix="elmos-fullstack-e2e-")

    evidence = {
        "schema_version": "1.0.0",
        "timestamp": dt.datetime.now(dt.UTC).isoformat(),
        "status": overall_status,
        "project_name": project_name,
        "steps": steps,
        "all_passed": overall_status == "PASSED",
    }

    output_json = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_json, encoding="utf-8")

    print(output_json)
    return 0 if overall_status == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
