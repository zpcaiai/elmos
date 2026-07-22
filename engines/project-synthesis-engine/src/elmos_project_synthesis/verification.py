from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _resolve_tool(name: str, fallback: str | None = None) -> str:
    found = shutil.which(name)
    if found:
        return found
    if fallback and Path(fallback).is_file():
        return fallback
    raise RuntimeError(f"REQUIRED_TOOL_NOT_FOUND:{name}")


def _run(command: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)  # noqa: S603
    output = (completed.stdout + completed.stderr)[-12000:]
    return {"command": command, "exit_code": completed.returncode, "output": output}


def _probe(command: list[str], cwd: Path, port: int, environment: dict[str, str] | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(environment or {})
    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    deadline = time.monotonic() + 30
    status = "FAILED"
    response = ""
    local_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                request = urllib.request.Request(f"http://127.0.0.1:{port}/health", method="GET")  # noqa: S310
                with local_opener.open(request, timeout=1) as result:
                    response = result.read().decode("utf-8")
                    if result.status == 200 and '"UP"' in response:
                        status = "PASSED"
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.25)
    finally:
        if process.poll() is None:
            if hasattr(os, "killpg"):
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                if hasattr(os, "killpg"):
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
        output = process.stdout.read()[-6000:] if process.stdout is not None else ""
        if process.stdout is not None:
            process.stdout.close()
    return {
        "command": command,
        "kind": "startup-probe",
        "port": port,
        "exit_code": 0 if status == "PASSED" else 1,
        "status": status,
        "response": response,
        "output": output,
    }


def verify_workspace(workspace: Path) -> dict[str, Any]:
    root = workspace.resolve(strict=True)
    ports = {"java": 8081, "python": 8082, "csharp": 8083}
    blueprint_path = root / "requirements" / "project-blueprint.json"
    if blueprint_path.is_file():
        blueprint = json.loads(blueprint_path.read_text(encoding="utf-8"))
        for application in blueprint.get("applications", []):
            language = application.get("language")
            port = application.get("port")
            if language in ports and isinstance(port, int):
                ports[language] = port
    results: list[dict[str, Any]] = []
    if (root / "java" / "pom.xml").is_file():
        results.append(_run([_resolve_tool("mvn", "/opt/homebrew/bin/mvn"), "-B", "package"], root / "java"))
    if (root / "python" / "pyproject.toml").is_file():
        uv = _resolve_tool("uv", "/opt/homebrew/bin/uv")
        results.extend(
            [
                _run([uv, "sync", "--python", "3.12"], root / "python"),
                _run([uv, "run", "pytest"], root / "python"),
                _run([uv, "run", "ruff", "check", "src", "tests"], root / "python"),
                _run([uv, "run", "mypy", "src"], root / "python"),
            ]
        )
    if any((root / "dotnet").glob("*.slnx")):
        dotnet = _resolve_tool("dotnet", "/opt/homebrew/bin/dotnet")
        results.extend(
            [
                _run([dotnet, "restore", "--use-lock-file"], root / "dotnet"),
                _run([dotnet, "test", "--no-restore", "-c", "Release"], root / "dotnet"),
            ]
        )
    if all(result["exit_code"] == 0 for result in results):
        java_jars = sorted((root / "java" / "target").glob("*.jar"))
        java_jars = [jar for jar in java_jars if not jar.name.endswith(".original")]
        if java_jars:
            results.append(
                _probe(
                    [_resolve_tool("java"), "-jar", str(java_jars[0])],
                    root / "java",
                    ports["java"],
                    {"PORT": str(ports["java"])},
                )
            )
        python_packages = sorted((root / "python" / "src").glob("*/__main__.py"))
        if python_packages:
            package_name = python_packages[0].parent.name
            results.append(
                _probe(
                    [_resolve_tool("uv", "/opt/homebrew/bin/uv"), "run", "python", "-m", package_name],
                    root / "python",
                    ports["python"],
                    {"PORT": str(ports["python"])},
                )
            )
        dotnet_projects = sorted((root / "dotnet" / "src").glob("*/*.csproj"))
        if dotnet_projects:
            results.append(
                _probe(
                    [
                        _resolve_tool("dotnet", "/opt/homebrew/bin/dotnet"),
                        "run",
                        "--no-build",
                        "-c",
                        "Release",
                        "--project",
                        str(dotnet_projects[0]),
                    ],
                    root / "dotnet",
                    ports["csharp"],
                    {"ASPNETCORE_URLS": f"http://127.0.0.1:{ports['csharp']}"},
                )
            )
    status = "PASSED" if results and all(result["exit_code"] == 0 for result in results) else "FAILED"
    return {
        "schema_version": "1.0.0",
        "status": status,
        "workspace": str(root),
        "environment": {"path": os.environ.get("PATH", "")},
        "production_delivery_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "results": results,
    }
