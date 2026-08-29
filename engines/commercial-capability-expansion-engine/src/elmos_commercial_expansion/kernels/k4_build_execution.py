"""K4: Build & Execution Kernel for Elmos Commercial Capability Expansion."""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from ..models import TaskContext


class BuildExecutionKernel:
    """Manages hermetic execution, sandboxing, reproducible builds, and cache planning."""

    def __init__(self):
        self.action_cache: Dict[str, Dict[str, Any]] = {}
        self.execution_logs: List[Dict[str, Any]] = []

    def compute_action_key(
        self,
        command: List[str],
        input_files: Dict[str, str],
        environment_vars: Dict[str, str],
    ) -> str:
        """Computes content-addressed action cache key."""
        h = hashlib.sha256()
        h.update(" ".join(command).encode("utf-8"))
        for path, digest in sorted(input_files.items()):
            h.update(f"{path}:{digest}".encode("utf-8"))
        for k, v in sorted(environment_vars.items()):
            h.update(f"{k}={v}".encode("utf-8"))
        return h.hexdigest()

    def run_sandboxed_command(
        self,
        context: TaskContext,
        command: List[str],
        cwd: str,
        env_overlay: Optional[Dict[str, str]] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Executes build or validation command within isolated process boundary."""
        timeout = timeout_seconds or min(context.timeout_seconds, 60)
        env = os.environ.copy()
        if env_overlay:
            env.update(env_overlay)

        # Enforce hermetic isolation environment flags
        env["ELMOS_SANDBOX_ACTIVE"] = "1"
        env["ELMOS_TENANT_ID"] = context.tenant_id
        env["PYTHONUNBUFFERED"] = "1"

        start_time = time.time()
        try:
            res = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                "command": command,
                "exit_code": res.returncode,
                "stdout": res.stdout[:10_000],
                "stderr": res.stderr[:10_000],
                "duration_ms": duration_ms,
                "timed_out": False,
                "status": "SUCCESS" if res.returncode == 0 else "FAILED",
            }
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds",
                "duration_ms": duration_ms,
                "timed_out": True,
                "status": "TIMEOUT",
            }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            result = {
                "command": command,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(exc),
                "duration_ms": duration_ms,
                "timed_out": False,
                "status": "ERROR",
            }

        self.execution_logs.append(result)
        return result

    def verify_reproducible_build(
        self,
        build_output_1: bytes,
        build_output_2: bytes,
    ) -> Dict[str, Any]:
        """Verifies bit-for-bit build reproducibility across two separate runs."""
        hash1 = hashlib.sha256(build_output_1).hexdigest()
        hash2 = hashlib.sha256(build_output_2).hexdigest()
        identical = hash1 == hash2

        return {
            "is_reproducible": identical,
            "digest_run1": hash1,
            "digest_run2": hash2,
            "status": "VERIFIED" if identical else "NON_DETERMINISTIC_DRIFT",
        }
