from __future__ import annotations

import datetime as dt
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


def environment_evidence() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "java_available": shutil.which("java") is not None,
        "javac_available": shutil.which("javac") is not None,
        "docker_available": shutil.which("docker") is not None,
    }


def execute_case(case: dict[str, Any], root: Path, *, allow_unavailable: bool = False) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    started_at = utc_now()
    start = time.perf_counter()
    adapter = case["execution"]["adapter"]
    status = "error"
    oracle_results: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"environment": environment_evidence(), "adapter": adapter}
    silent = False
    try:
        executor = EXECUTORS.get(adapter)
        if executor is None:
            status = "unavailable" if allow_unavailable else "skipped"
            oracle_results = [{"type": "adapter-availability", "passed": False, "reason": f"adapter '{adapter}' requires the Elmos production harness"}]
            evidence["required_adapter"] = adapter
        else:
            status, oracle_results, adapter_evidence, silent = executor(case, root)
            evidence.update(adapter_evidence)
    except TimeoutError as exc:
        status = "error"
        oracle_results = [{"type": "execution-timeout", "passed": False, "message": str(exc)}]
    except Exception as exc:
        status = "error"
        oracle_results = [{"type": "runner-error", "passed": False, "error_type": type(exc).__name__, "message": str(exc)}]
    duration_ms = int((time.perf_counter() - start) * 1000)
    return {
        "schema_version": "1.0", "run_id": run_id, "case_id": case["id"], "business_line": case["business_line"],
        "priority": case["priority"], "level": case["level"], "status": status,
        "started_at": started_at, "finished_at": utc_now(), "duration_ms": duration_ms,
        "oracle_results": oracle_results, "evidence": evidence, "silent_semantic_error": silent,
        "cost": {"token_input": 0, "token_output": 0, "credit_usd": 0.0, "wall_clock_ms": duration_ms},
    }


def run_cases(cases: list[dict[str, Any]], root: Path, *, allow_unavailable: bool = False) -> list[dict[str, Any]]:
    return [execute_case(case, root, allow_unavailable=allow_unavailable) for case in cases]
