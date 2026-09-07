from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from etgb.normalize import first_difference, normalize, remove_json_paths


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def run_shell(command: str, cwd: Path, timeout: int, env: dict[str, str] | None = None) -> dict[str, Any]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        executable="/bin/bash",
        text=True,
        capture_output=True,
        timeout=timeout,
        env=merged_env,
    )
    return {
        "command": command,
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": _digest(completed.stdout),
        "stderr_sha256": _digest(completed.stderr),
    }


def _parse_json_output(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("process produced empty stdout")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        for line in reversed(stripped.splitlines()):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        raise ValueError("stdout does not contain a JSON value")


def execute_local_process(case: dict[str, Any], root: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    result = run_shell(spec["command"], root / spec["cwd"], spec["timeout_seconds"], spec.get("env"))
    passed = result["returncode"] == 0
    oracle = {"type": "process-success", "passed": passed, "returncode": result["returncode"]}
    return ("passed" if passed else "failed", [oracle], {"process": result}, False)


def execute_differential_process(case: dict[str, Any], root: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    source = run_shell(spec["source_command"], root / spec["source_cwd"], spec["timeout_seconds"], spec.get("source_env"))
    target = run_shell(spec["target_command"], root / spec["target_cwd"], spec["timeout_seconds"], spec.get("target_env"))
    build_pass = source["returncode"] == 0 and target["returncode"] == 0
    oracles: list[dict[str, Any]] = [{"type": "both-processes-success", "passed": build_pass, "source_returncode": source["returncode"], "target_returncode": target["returncode"]}]
    semantic_pass = False
    diff: dict[str, Any] | None = None
    source_value: Any = None
    target_value: Any = None
    if build_pass:
        try:
            source_value = normalize(_parse_json_output(source["stdout"]))
            target_value = normalize(_parse_json_output(target["stdout"]))
            diff = first_difference(source_value, target_value)
            semantic_pass = diff is None
        except Exception as exc:  # evidence path, not process crash
            diff = {"reason": "output-parse-error", "message": str(exc)}
    oracles.append({"type": "json-stdout-equivalence", "passed": semantic_pass, "first_difference": diff})
    passed = build_pass and semantic_pass
    silent = build_pass and not semantic_pass
    evidence = {"source_process": source, "target_process": target, "normalized_source": source_value, "normalized_target": target_value, "first_difference": diff}
    return ("passed" if passed else "failed", oracles, evidence, silent)


def execute_json_file_differential(case: dict[str, Any], root: Path) -> tuple[str, list[dict[str, Any]], dict[str, Any], bool]:
    spec = case["execution"]
    source_path = root / spec["source_path"]
    target_path = root / spec["target_path"]
    source_value = json.loads(source_path.read_text(encoding="utf-8"))
    target_value = json.loads(target_path.read_text(encoding="utf-8"))
    ignore = spec.get("ignore_paths", [])
    source_value = normalize(remove_json_paths(source_value, ignore))
    target_value = normalize(remove_json_paths(target_value, ignore))
    diff = first_difference(source_value, target_value)
    passed = diff is None
    oracle = {"type": "json-file-equivalence", "passed": passed, "first_difference": diff, "ignored_paths": ignore}
    evidence = {"source_path": str(source_path), "target_path": str(target_path), "normalized_source": source_value, "normalized_target": target_value}
    return ("passed" if passed else "failed", [oracle], evidence, not passed)
