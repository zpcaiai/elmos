from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from etgb.adapters.process import execute_differential_process, execute_json_file_differential, execute_local_process
from etgb.adapters.sqlite import execute_sqlite_differential

EXECUTORS = {
    "local-process": execute_local_process,
    "differential-process": execute_differential_process,
    "json-file-differential": execute_json_file_differential,
    "sqlite-differential": execute_sqlite_differential,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest_value(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def environment_evidence() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "java_available": shutil.which("java") is not None,
        "javac_available": shutil.which("javac") is not None,
        "docker_available": shutil.which("docker") is not None,
    }


def _commands(adapter_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for key, value in adapter_evidence.items():
        if isinstance(value, dict) and "command" in value:
            commands.append(
                {
                    "name": key,
                    "command": value.get("command"),
                    "cwd": value.get("cwd"),
                    "returncode": value.get("returncode"),
                    "stdout_sha256": value.get("stdout_sha256"),
                    "stderr_sha256": value.get("stderr_sha256"),
                }
            )
    return commands


def execute_case(case: dict[str, Any], root: Path, *, allow_unavailable: bool = False) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started_at = utc_now()
    start = time.perf_counter()
    adapter = case["execution"]["adapter"]
    status = "error"
    oracle_results: list[dict[str, Any]] = []
    environment = environment_evidence()
    adapter_evidence: dict[str, Any] = {}
    silent = False
    try:
        executor = EXECUTORS.get(adapter)
        if executor is None:
            status = "unavailable" if allow_unavailable else "skipped"
            oracle_results = [
                {
                    "type": "adapter-availability",
                    "passed": False,
                    "critical": case.get("priority") == "P0",
                    "reason": f"adapter '{adapter}' requires the Elmos production harness",
                }
            ]
            adapter_evidence["required_adapter"] = adapter
        else:
            status, oracle_results, adapter_evidence, silent = executor(case, root)
            for oracle in oracle_results:
                oracle.setdefault("critical", case.get("priority") == "P0")
    except TimeoutError as exc:
        status = "error"
        oracle_results = [{"type": "execution-timeout", "passed": False, "critical": True, "message": str(exc)}]
    except Exception as exc:
        status = "error"
        oracle_results = [
            {
                "type": "runner-error",
                "passed": False,
                "critical": True,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        ]
    duration_ms = int((time.perf_counter() - start) * 1000)
    package_version = (root / "VERSION").read_text(encoding="utf-8").strip() if (root / "VERSION").exists() else "unknown"
    cost = {"token_input": 0, "token_output": 0, "credit_usd": 0.0, "wall_clock_ms": duration_ms}
    evidence = {
        "environment": environment,
        "adapter": adapter,
        "input_digest": digest_value(case),
        "source_commit": case.get("source", {}).get("commit") or case.get("provenance", {}).get("source_commit") or "fixture-or-matrix",
        "toolchain_digest": digest_value(environment),
        "model_version": "local-reference-runner",
        "skill_version": package_version,
        "commands": _commands(adapter_evidence),
        "stdout_stderr": {
            key: {
                "stdout_sha256": value.get("stdout_sha256"),
                "stderr_sha256": value.get("stderr_sha256"),
            }
            for key, value in adapter_evidence.items()
            if isinstance(value, dict) and ("stdout_sha256" in value or "stderr_sha256" in value)
        },
        "oracle_results_digest": digest_value(oracle_results),
        "cost": cost,
        "wall_clock_ms": duration_ms,
        "artifacts_digest": digest_value(adapter_evidence),
        "integrity_valid": True,
        "authority_valid": True,
        "adapter_evidence": adapter_evidence,
    }
    return {
        "schema_version": "1.1",
        "run_id": run_id,
        "case_id": case["id"],
        "capability_id": case.get("coverage", {}).get("capability_id"),
        "business_line": case["business_line"],
        "priority": case["priority"],
        "level": case["level"],
        "seed": case.get("execution", {}).get("seed"),
        "status": status,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_ms": duration_ms,
        "oracle_results": oracle_results,
        "evidence": evidence,
        "silent_semantic_error": silent,
        "cost": cost,
    }


def run_cases(cases: list[dict[str, Any]], root: Path, *, allow_unavailable: bool = False) -> list[dict[str, Any]]:
    return [execute_case(case, root, allow_unavailable=allow_unavailable) for case in cases]
