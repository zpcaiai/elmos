#!/usr/bin/env python3
"""Run real local repository checks without manufacturing case certification."""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _common import canonical_bytes, load_json, sha256_bytes, sha256_file


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED_PARTS = {
    ".git",
    ".idea",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "artifacts",
    "node_modules",
    "target",
    "bin",
    "obj",
    "TestResults",
}
DERIVED_EVIDENCE_PATHS = {
    Path("docs/test-suite/ELMOS_VALIDATION_REPORT.md"),
    Path("test-suites/batch1-37-strict/release-gate.json"),
    Path("test-suites/batch1-55-slightly-strict/release-gate.json"),
    Path("test-suites/batch1-65-slightly-strict/release-gate.json"),
}


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def git_paths(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    paths = []
    for raw in completed.stdout.split(b"\x00"):
        if not raw:
            continue
        relative = Path(os.fsdecode(raw))
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if relative in DERIVED_EVIDENCE_PATHS:
            continue
        path = root / relative
        if path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda item: str(item.relative_to(root)))


def command_output(command: list[str], root: Path) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {exc}"
    output = (completed.stdout + completed.stderr).strip()
    return output.splitlines()[0] if output else f"exit={completed.returncode}"


def source_entries(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": str(path.relative_to(root)),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }
        for path in git_paths(root)
    ]


def source_drift(
    before: list[dict[str, Any]], after: list[dict[str, Any]]
) -> dict[str, list[str]]:
    before_by_path = {entry["path"]: (entry["sha256"], entry["bytes"]) for entry in before}
    after_by_path = {entry["path"]: (entry["sha256"], entry["bytes"]) for entry in after}
    before_paths = set(before_by_path)
    after_paths = set(after_by_path)
    return {
        "added": sorted(after_paths - before_paths),
        "removed": sorted(before_paths - after_paths),
        "changed": sorted(
            path
            for path in before_paths & after_paths
            if before_by_path[path] != after_by_path[path]
        ),
    }


def validate_plan(plan: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict) or plan.get("plan_version") != 1:
        return ["plan_version must be 1"]
    if plan.get("scope") != "local-engineering-evidence-only":
        errors.append("plan scope must remain local-engineering-evidence-only")
    if plan.get("updates_certification_cases") is not False:
        errors.append("local qualification cannot update certification cases")
    if plan.get("certification_case_ids") != []:
        errors.append("local qualification certification_case_ids must be empty")
    commands = plan.get("commands")
    if not isinstance(commands, list) or not commands:
        errors.append("plan requires commands")
        return errors
    ids: list[str] = []
    for index, item in enumerate(commands):
        if not isinstance(item, dict):
            errors.append(f"commands[{index}] must be an object")
            continue
        identifier = item.get("id")
        command = item.get("command")
        timeout = item.get("timeout_seconds")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"commands[{index}].id is required")
        else:
            ids.append(identifier)
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) or not arg for arg in command):
            errors.append(f"commands[{index}].command must be a non-empty argument array")
        if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout < 1 or timeout > 7200:
            errors.append(f"commands[{index}].timeout_seconds must be 1..7200")
        cleanup = item.get("cleanup_after")
        if cleanup is not None:
            if not isinstance(cleanup, dict):
                errors.append(f"commands[{index}].cleanup_after must be an object")
            else:
                cleanup_command = cleanup.get("command")
                cleanup_timeout = cleanup.get("timeout_seconds")
                if (
                    not isinstance(cleanup_command, list)
                    or not cleanup_command
                    or any(not isinstance(arg, str) or not arg for arg in cleanup_command)
                ):
                    errors.append(
                        f"commands[{index}].cleanup_after.command must be a non-empty argument array"
                    )
                if (
                    not isinstance(cleanup_timeout, int)
                    or isinstance(cleanup_timeout, bool)
                    or cleanup_timeout < 1
                    or cleanup_timeout > 1800
                ):
                    errors.append(
                        f"commands[{index}].cleanup_after.timeout_seconds must be 1..1800"
                    )
    if len(ids) != len(set(ids)):
        errors.append("command ids must be unique")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan",
        default="test-suites/batch1-37-strict/repository-qualification-plan.json",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--root", default=str(REPOSITORY_ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    plan_path = (root / args.plan).resolve() if not Path(args.plan).is_absolute() else Path(args.plan).resolve()
    output = Path(args.output).resolve()
    if output.exists():
        print(f"REFUSED: output already exists and is immutable: {output}", file=sys.stderr)
        return 2
    plan = load_json(plan_path)
    errors = validate_plan(plan)
    if errors:
        print("INVALID PLAN\n" + "\n".join(errors), file=sys.stderr)
        return 2
    output.mkdir(parents=True)
    logs = output / "logs"
    logs.mkdir()

    initial_entries = source_entries(root)
    artifact_manifest = {
        "manifest_version": 1,
        "phase": "pre-run",
        "repository": str(root),
        "git_head": command_output(["git", "rev-parse", "HEAD"], root),
        "git_status": command_output(["git", "status", "--porcelain=v1"], root),
        "files": initial_entries,
    }
    artifact_path = output / "artifact-manifest.json"
    artifact_path.write_text(json.dumps(artifact_manifest, ensure_ascii=False, indent=2) + "\n")
    environment = {
        "environment_id": "elmos-local-engineering-qualification",
        "captured_at": iso_now(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version,
        "java": command_output(["java", "-version"], root),
        "maven": command_output(["/opt/homebrew/bin/mvn", "-version"], root),
        "dotnet": command_output(["dotnet", "--version"], root),
        "node": command_output(["node", "--version"], root),
        "network_policy": "build-tool-managed; no production operations authorized",
        "production_data": False,
        "secrets": "references-only",
    }
    environment_path = output / "environment-manifest.json"
    environment_path.write_text(json.dumps(environment, ensure_ascii=False, indent=2) + "\n")

    command_results: list[dict[str, Any]] = []
    started_at = iso_now()
    for item in plan["commands"]:
        command_started = iso_now()
        try:
            completed = subprocess.run(
                item["command"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=item["timeout_seconds"],
            )
            output_text = completed.stdout + completed.stderr
            exit_code = completed.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            output_text = stdout + stderr + "\nTIMEOUT\n"
            exit_code = 124
            timed_out = True
        cleanup = item.get("cleanup_after")
        cleanup_result: dict[str, Any] | None = None
        if cleanup is not None:
            cleanup_started = iso_now()
            try:
                cleanup_completed = subprocess.run(
                    cleanup["command"],
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=cleanup["timeout_seconds"],
                )
                cleanup_text = cleanup_completed.stdout + cleanup_completed.stderr
                cleanup_exit_code = cleanup_completed.returncode
                cleanup_timed_out = False
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                cleanup_text = stdout + stderr + "\nTIMEOUT\n"
                cleanup_exit_code = 124
                cleanup_timed_out = True

            # Cleanup runs before log persistence so large, reproducible build
            # outputs cannot consume the remaining disk space needed for the
            # immutable qualification evidence itself.
            cleanup_log_path = logs / f"{item['id']}.cleanup.log"
            cleanup_result = {
                "command": cleanup["command"],
                "started_at": cleanup_started,
                "finished_at": iso_now(),
                "exit_code": cleanup_exit_code,
                "timed_out": cleanup_timed_out,
                "log": str(cleanup_log_path.relative_to(output)),
            }

        log_path = logs / f"{item['id']}.log"
        log_path.write_text(output_text, encoding="utf-8")
        command_result = {
            "id": item["id"],
            "command": item["command"],
            "started_at": command_started,
            "finished_at": iso_now(),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "log": str(log_path.relative_to(output)),
            "log_sha256": sha256_file(log_path),
            "log_bytes": log_path.stat().st_size,
        }
        if cleanup_result is not None:
            cleanup_log_path.write_text(cleanup_text, encoding="utf-8")
            cleanup_result["log_sha256"] = sha256_file(cleanup_log_path)
            cleanup_result["log_bytes"] = cleanup_log_path.stat().st_size
            command_result["cleanup_after"] = cleanup_result
        command_results.append(command_result)
    final_entries = source_entries(root)
    post_run_manifest = {
        "manifest_version": 1,
        "phase": "post-run",
        "repository": str(root),
        "git_head": command_output(["git", "rev-parse", "HEAD"], root),
        "git_status": command_output(["git", "status", "--porcelain=v1"], root),
        "files": final_entries,
    }
    post_run_path = output / "post-run-artifact-manifest.json"
    post_run_path.write_text(json.dumps(post_run_manifest, ensure_ascii=False, indent=2) + "\n")
    drift = source_drift(initial_entries, final_entries)
    source_snapshot_consistent = not any(drift.values())
    passed = (
        all(
            item["exit_code"] == 0
            and item.get("cleanup_after", {}).get("exit_code", 0) == 0
            for item in command_results
        )
        and source_snapshot_consistent
    )
    report = {
        "report_version": 1,
        "plan_id": plan["plan_id"],
        "scope": plan["scope"],
        "status": "PASSED" if passed else "FAILED",
        "started_at": started_at,
        "finished_at": iso_now(),
        "artifact_manifest": {
            "path": artifact_path.name,
            "sha256": sha256_file(artifact_path),
        },
        "post_run_artifact_manifest": {
            "path": post_run_path.name,
            "sha256": sha256_file(post_run_path),
        },
        "source_snapshot_consistent": source_snapshot_consistent,
        "source_drift": drift,
        "environment_manifest": {
            "path": environment_path.name,
            "sha256": sha256_file(environment_path),
        },
        "plan_digest": "sha256:" + sha256_file(plan_path),
        "commands": command_results,
        "certification_case_updates": [],
        "certification_decision": "BLOCKED",
        "field_evidence_status": "NOT_RUN",
        "boundary": "Local engineering checks do not satisfy the 408 exact certification cases.",
    }
    report["report_digest"] = "sha256:" + sha256_bytes(canonical_bytes(report))
    report_path = output / "qualification-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
