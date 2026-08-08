#!/usr/bin/env python3
"""Generated-project local verification and lifecycle controller.

The module is emitted verbatim into generated workspaces.  It executes only
allowlisted local tools with argument arrays, verifies every managed file
before execution, binds published ports to loopback through the generated
Compose file, and records bounded health evidence without treating it as
production certification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_TARGET = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_MAX_JSON_BYTES = 1_048_576
_MAX_HEALTH_BYTES = 65_536
_SUPPORTED_COMMANDS = {
    "java": "java",
    "python": "python",
    "csharp": "dotnet",
    "typescript": "typescript",
    "go": "go",
    "kotlin": "kotlin",
    "php": "php",
    "rust": "rust",
}
_TARGET_TOOLS = {
    "java": "mvn",
    "python": "uv",
    "csharp": "dotnet",
    "typescript": "pnpm",
    "go": "go",
    "kotlin": "gradle",
    "php": "composer",
    "rust": "cargo",
}


class LocalControlError(RuntimeError):
    """A fail-closed local lifecycle validation or execution error."""


def _load_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise LocalControlError(f"JSON_FILE_UNSAFE:{path}")
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise LocalControlError(f"JSON_FILE_TOO_LARGE:{path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LocalControlError(f"JSON_FILE_INVALID:{path}") from error
    if not isinstance(value, dict):
        raise LocalControlError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _safe_managed_path(root: Path, raw: str) -> Path:
    relative = PurePosixPath(raw)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise LocalControlError(f"MANAGED_PATH_UNSAFE:{raw}")
    candidate = root.joinpath(*relative.parts)
    ancestor = candidate.parent
    while ancestor != root:
        if ancestor.is_symlink():
            raise LocalControlError(f"MANAGED_PATH_SYMLINK_PARENT:{raw}")
        if root not in ancestor.parents:
            raise LocalControlError(f"MANAGED_PATH_ESCAPE:{raw}")
        ancestor = ancestor.parent
    parent = candidate.parent.resolve(strict=False)
    if root not in (parent, *parent.parents):
        raise LocalControlError(f"MANAGED_PATH_ESCAPE:{raw}")
    return candidate


def _verify_managed_workspace(root: Path) -> dict[str, Any]:
    manifest = _load_json(_safe_managed_path(root, ".elmos/generation-manifest.json"))
    if manifest.get("engine") != "elmos.project-synthesis" or manifest.get("status") != "GENERATED":
        raise LocalControlError("GENERATION_MANIFEST_IDENTITY_INVALID")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise LocalControlError("GENERATION_MANIFEST_FILES_INVALID")
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise LocalControlError("GENERATION_MANIFEST_ENTRY_INVALID")
        raw_path = entry.get("path")
        digest = entry.get("sha256")
        if (
            not isinstance(raw_path, str)
            or raw_path in seen
            or not isinstance(digest, str)
            or _DIGEST.fullmatch(digest) is None
        ):
            raise LocalControlError("GENERATION_MANIFEST_ENTRY_INVALID")
        seen.add(raw_path)
        target = _safe_managed_path(root, raw_path)
        if target.is_symlink() or not target.is_file():
            raise LocalControlError(f"MANAGED_FILE_UNSAFE:{raw_path}")
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise LocalControlError(f"MANAGED_FILE_INTEGRITY_MISMATCH:{raw_path}")
    return manifest


def _applications(root: Path) -> tuple[str, list[dict[str, Any]]]:
    blueprint = _load_json(_safe_managed_path(root, "requirements/project-blueprint.json"))
    project = blueprint.get("project")
    applications = blueprint.get("applications")
    if (
        not isinstance(project, dict)
        or not isinstance(project.get("name"), str)
        or _TARGET.fullmatch(project["name"]) is None
        or not isinstance(applications, list)
        or not applications
    ):
        raise LocalControlError("PROJECT_BLUEPRINT_INVALID")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for application in applications:
        if not isinstance(application, dict):
            raise LocalControlError("PROJECT_APPLICATION_INVALID")
        language = application.get("language")
        port = application.get("port")
        if (
            not isinstance(language, str)
            or language not in _SUPPORTED_COMMANDS
            or language in seen
            or not isinstance(port, int)
            or isinstance(port, bool)
            or not 1024 <= port <= 65535
        ):
            raise LocalControlError("PROJECT_APPLICATION_INVALID")
        directory = root / _SUPPORTED_COMMANDS[language]
        if directory.is_symlink() or not directory.is_dir():
            raise LocalControlError(f"TARGET_DIRECTORY_UNSAFE:{language}")
        seen.add(language)
        normalized.append(application)
    return project["name"], normalized


def _resolve_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None or Path(executable).name != name:
        raise LocalControlError(f"REQUIRED_TOOL_NOT_FOUND:{name}")
    resolved = Path(executable).resolve(strict=True)
    if not resolved.is_file():
        raise LocalControlError(f"REQUIRED_TOOL_UNSAFE:{name}")
    return str(Path(executable))


def _run(
    command: list[str],
    *,
    cwd: Path,
    timeout: int | None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(  # noqa: S603 - executable is resolved and arguments are structured.
            command,
            cwd=cwd,
            check=False,
            text=True,
            capture_output=capture,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise LocalControlError(f"COMMAND_TIMEOUT:{Path(command[0]).name}:{timeout}") from error
    if completed.returncode != 0:
        detail = ""
        if capture:
            detail = (completed.stderr or completed.stdout or "")[-2_000:].replace("\n", " ")
        raise LocalControlError(f"COMMAND_FAILED:{Path(command[0]).name}:{completed.returncode}:{detail}")
    return completed


def _target(root: Path, applications: list[dict[str, Any]], selected: str | None) -> dict[str, Any]:
    language = selected or str(applications[0]["language"])
    match = next((item for item in applications if item.get("language") == language), None)
    if match is None:
        raise LocalControlError(f"TARGET_NOT_GENERATED:{language}")
    return match


def _make(root: Path, application: dict[str, Any], goal: str) -> None:
    make = _resolve_tool("make")
    language = str(application["language"])
    directory = root / _SUPPORTED_COMMANDS[language]
    _run([make, "-C", str(directory), goal], cwd=root, timeout=None)


def _docker(
    root: Path,
    arguments: list[str],
    *,
    timeout: int,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    docker = _resolve_tool("docker")
    return _run(
        [docker, "compose", "-f", str(root / "docker-compose.yml"), *arguments],
        cwd=root,
        timeout=timeout,
        capture=capture,
    )


def _probe(url: str, expected_service: str) -> float:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    started = time.perf_counter()
    request = urllib.request.Request(url, method="GET")  # noqa: S310 - fixed loopback URL from validated blueprint.
    try:
        with opener.open(request, timeout=2) as response:
            raw = response.read(_MAX_HEALTH_BYTES + 1)
            if len(raw) > _MAX_HEALTH_BYTES:
                raise LocalControlError("HEALTH_RESPONSE_TOO_LARGE")
            payload = json.loads(raw.decode("utf-8"))
            if (
                response.status != 200
                or not isinstance(payload, dict)
                or payload.get("status") != "UP"
                or payload.get("service") != expected_service
            ):
                raise LocalControlError("HEALTH_IDENTITY_MISMATCH")
    except (OSError, UnicodeError, json.JSONDecodeError, urllib.error.URLError) as error:
        raise LocalControlError("HEALTH_REQUEST_FAILED") from error
    return (time.perf_counter() - started) * 1_000


def _wait_for_health(project: str, applications: list[dict[str, Any]], *, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    pending = {str(item["language"]): item for item in applications}
    latencies: dict[str, list[float]] = {language: [] for language in pending}
    last_error = "HEALTH_NOT_OBSERVED"
    while pending and time.monotonic() < deadline:
        for language, application in list(pending.items()):
            try:
                latency = _probe(f"http://127.0.0.1:{application['port']}/health", project)
            except LocalControlError as error:
                last_error = str(error)
                continue
            latencies[language].append(latency)
            del pending[language]
        if pending:
            time.sleep(0.25)
    if pending:
        raise LocalControlError(f"RUNTIME_HEALTH_TIMEOUT:{','.join(sorted(pending))}:{last_error}")
    return {
        "status": "PASSED",
        "service": project,
        "targets": {
            language: {"health": "PASSED", "latency_ms": round(values[-1], 3)}
            for language, values in sorted(latencies.items())
        },
    }


def _smoke(project: str, applications: list[dict[str, Any]], *, requests: int) -> dict[str, Any]:
    if not 3 <= requests <= 100:
        raise LocalControlError("SMOKE_REQUEST_COUNT_OUT_OF_RANGE")
    results: dict[str, Any] = {}
    for application in applications:
        language = str(application["language"])
        samples = [
            _probe(f"http://127.0.0.1:{application['port']}/health", project)
            for _ in range(requests)
        ]
        ordered = sorted(samples)
        percentile_index = max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))
        p95 = ordered[percentile_index]
        results[language] = {
            "requests": requests,
            "failures": 0,
            "p95_ms": round(p95, 3),
            "health_budget_ms": 500,
            "status": "PASSED" if p95 <= 500 else "FAILED",
        }
    status = "PASSED" if all(item["status"] == "PASSED" for item in results.values()) else "FAILED"
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.local-health-smoke",
        "status": status,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "targets": results,
        "evidence_class": "LOCAL_ENGINEERING",
        "production_delivery_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise LocalControlError("EVIDENCE_OUTPUT_UNSAFE")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="projectctl")
    parser.add_argument("action", choices=("doctor", "verify", "run", "plan", "up", "down", "status", "smoke"))
    parser.add_argument("--target")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--requests", type=int, default=5)
    parser.add_argument("--evidence", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path(__file__).resolve(strict=True).parents[1]
    try:
        manifest = _verify_managed_workspace(root)
        project, applications = _applications(root)
        selected = _target(root, applications, args.target)
        if not 5 <= args.timeout <= 1_800:
            raise LocalControlError("TIMEOUT_OUT_OF_RANGE")
        if args.action == "doctor":
            toolchains = {
                str(application["language"]): _resolve_tool(_TARGET_TOOLS[str(application["language"])])
                for application in applications
            }
            output = {
                "status": "READY",
                "project": project,
                "engine_version": manifest.get("engine_version"),
                "python": sys.version.split()[0],
                "make": _resolve_tool("make"),
                "docker": shutil.which("docker"),
                "toolchains": toolchains,
                "selected_target": selected["language"],
                "managed_integrity": "PASSED",
            }
        elif args.action in {"verify", "run"}:
            targets = applications if args.all else [selected]
            if args.action == "run" and len(targets) != 1:
                raise LocalControlError("RUN_REQUIRES_EXACTLY_ONE_TARGET")
            for application in targets:
                _make(root, application, "test" if args.action == "verify" else "run")
            output = {"status": "PASSED", "action": args.action, "targets": [item["language"] for item in targets]}
        elif args.action == "plan":
            _docker(root, ["config", "--quiet"], timeout=30)
            output = {
                "status": "READY",
                "action": "compose-up",
                "targets": [item["language"] for item in applications],
                "published_host": "127.0.0.1",
                "runtime_network": "internal",
                "managed_integrity": "PASSED",
                "external_execution": "NOT_RUN",
            }
        elif args.action == "up":
            unsupported = [
                str(item["language"])
                for item in applications
                if item.get("storage") != "in-memory" or item.get("auth_mode") != "none"
            ]
            if unsupported:
                raise LocalControlError(
                    "COMPOSE_DEVELOPMENT_PROFILE_UNAVAILABLE_USE_NATIVE_RUN:" + ",".join(unsupported)
                )
            _docker(root, ["config", "--quiet"], timeout=30)
            try:
                _docker(root, ["up", "--build", "--detach", "--remove-orphans"], timeout=1_800)
                output = _wait_for_health(project, applications, timeout=args.timeout)
            except (LocalControlError, OSError, KeyboardInterrupt):
                try:
                    _docker(root, ["down", "--remove-orphans"], timeout=120)
                except LocalControlError:
                    pass
                raise
        elif args.action == "down":
            _docker(root, ["down", "--remove-orphans"], timeout=120)
            output = {"status": "STOPPED", "targets": [item["language"] for item in applications]}
        elif args.action == "status":
            output = _wait_for_health(project, applications, timeout=min(args.timeout, 10))
        else:
            output = _smoke(project, applications, requests=args.requests)
            if output["status"] != "PASSED":
                output["reason"] = "LOCAL_HEALTH_PERFORMANCE_BUDGET_FAILED"
        if args.evidence:
            evidence = args.evidence.expanduser().resolve(strict=False)
            if evidence == root or not evidence.is_relative_to(root):
                raise LocalControlError("EVIDENCE_OUTPUT_OUTSIDE_WORKSPACE")
            _write_json(evidence, output)
        if output.get("status") == "FAILED":
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
            return 2
        print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"status": "STOPPED", "reason": "INTERRUPTED_BY_USER"}), file=sys.stderr)
        return 130
    except (LocalControlError, OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
