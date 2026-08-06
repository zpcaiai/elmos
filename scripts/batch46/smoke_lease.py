#!/usr/bin/env python3
"""Runtime lease for one-click smoke runs.

A smoke run is a *lease*, not a deployment. The default free quota is 10
minutes; when it expires the lease terminates every service it started, removes
the ephemeral data it created, and records the outcome. Nothing survives an
expired lease — that is the contract that makes it safe to hand a generated
project to a user and say "just run it".

Rules:
  - The quota is enforced by a watchdog that runs independently of the
    application under test. An app that ignores SIGTERM is killed after the
    grace period.
  - Extension is explicit only. Auto-renew does not exist. Seconds granted
    beyond the free quota are recorded as `billable_seconds` for the metering
    boundary in docs/batch46/RUNTIME_LEASE_POLICY.md.
  - Teardown is idempotent and always writes a result, including on crash,
    Ctrl-C, and expiry.

CLI:
    python3 smoke_lease.py start  --project . --ttl 600
    python3 smoke_lease.py status --project .
    python3 smoke_lease.py extend --project . --seconds 300 --reason "..." --actor "..."
    python3 smoke_lease.py stop   --project . --reason manual
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from smoke_common import (
    DEFAULT_FREE_QUOTA_SECONDS,
    daemon_unreachable,
    DEFAULT_GRACE_SECONDS,
    SCHEMA_PREFIX,
    read_json,
    smoke_dir,
    utc_now,
    write_json,
)

RUNTIME_DIRNAME = "runtime"
LEASE_FILE = "lease.json"
LEASE_RESULT_FILE = "lease-result.json"


def runtime_dir(project_root: Path) -> Path:
    path = smoke_dir(project_root) / RUNTIME_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def lease_path(project_root: Path) -> Path:
    return runtime_dir(project_root) / LEASE_FILE


def new_lease(
    project_root: Path,
    ttl_seconds: int = DEFAULT_FREE_QUOTA_SECONDS,
    grace_seconds: int = DEFAULT_GRACE_SECONDS,
    entry: str = "script",
) -> dict[str, Any]:
    started = time.time()
    lease = {
        "schema": f"{SCHEMA_PREFIX}.runtime-lease/1",
        "lease_id": f"smoke-{int(started)}-{os.getpid()}",
        "entry": entry,
        "state": "active",
        "started_at": utc_now(),
        "started_monotonic": started,
        "free_quota_seconds": DEFAULT_FREE_QUOTA_SECONDS,
        "ttl_seconds": int(ttl_seconds),
        "grace_seconds": int(grace_seconds),
        "expires_at_epoch": started + int(ttl_seconds),
        "extensions": [],
        "billable_seconds": max(0, int(ttl_seconds) - DEFAULT_FREE_QUOTA_SECONDS),
        "extend_policy": "explicit-only",
        "auto_renew": False,
        "on_expiry": [
            "stop_application_processes",
            "stop_and_remove_containers_and_volumes",
            "delete_ephemeral_data",
            "release_ports",
            "write_lease_result",
        ],
        "managed_processes": [],
        "managed_compose_files": [],
        "managed_paths": [],
    }
    write_json(lease_path(project_root), lease)
    return lease


def load_lease(project_root: Path) -> dict[str, Any] | None:
    path = lease_path(project_root)
    return read_json(path) if path.is_file() else None


def save_lease(project_root: Path, lease: dict[str, Any]) -> None:
    write_json(lease_path(project_root), lease)


def remaining_seconds(lease: dict[str, Any]) -> float:
    return max(0.0, float(lease["expires_at_epoch"]) - time.time())


def extend(project_root: Path, seconds: int, reason: str, actor: str) -> dict[str, Any]:
    lease = load_lease(project_root)
    if not lease:
        raise SystemExit("error: no active lease for this project")
    if lease.get("state") != "active":
        raise SystemExit(f"error: lease is {lease.get('state')}; start a new run instead of extending")
    if seconds <= 0:
        raise SystemExit("error: --seconds must be positive")
    if not reason or not actor:
        raise SystemExit("error: --reason and --actor are required; extensions are explicit and attributable")
    lease["ttl_seconds"] = int(lease["ttl_seconds"]) + int(seconds)
    lease["expires_at_epoch"] = float(lease["expires_at_epoch"]) + int(seconds)
    lease["billable_seconds"] = max(0, int(lease["ttl_seconds"]) - int(lease["free_quota_seconds"]))
    lease["extensions"].append({
        "granted_at": utc_now(),
        "seconds": int(seconds),
        "reason": reason,
        "actor": actor,
        "beyond_free_quota": lease["billable_seconds"] > 0,
    })
    save_lease(project_root, lease)
    return lease


class LeaseWatchdog:
    """Terminates everything the smoke run started once the lease expires."""

    def __init__(
        self,
        project_root: Path,
        lease: dict[str, Any],
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.project_root = Path(project_root)
        self.lease = lease
        self.log = log or (lambda message: print(message, flush=True))
        self._processes: list[subprocess.Popen] = []
        self._compose_files: list[Path] = []
        self._paths: list[Path] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._reason = "expired"
        self._teardown_done = threading.Event()
        self._teardown_lock = threading.Lock()
        self.teardown_report: dict[str, Any] = {}

    # registration -------------------------------------------------------
    def track_process(self, process: subprocess.Popen, label: str = "") -> None:
        self._processes.append(process)
        self.lease["managed_processes"].append({"pid": process.pid, "label": label})
        save_lease(self.project_root, self.lease)

    def track_compose(self, compose_file: Path) -> None:
        self._compose_files.append(Path(compose_file))
        self.lease["managed_compose_files"].append(str(compose_file))
        save_lease(self.project_root, self.lease)

    def track_path(self, path: Path) -> None:
        self._paths.append(Path(path))
        self.lease["managed_paths"].append(str(path))
        save_lease(self.project_root, self.lease)

    # lifecycle ----------------------------------------------------------
    def start(self) -> None:
        self._thread = threading.Thread(target=self._watch, name="smoke-lease-watchdog", daemon=True)
        self._thread.start()

    def _refresh_from_disk(self) -> None:
        """Pick up an extension granted by `smoke_lease.py extend` in another process.

        The watchdog holds the lease in memory, so without this an extension
        would be recorded but never honoured — the run would die on the original
        deadline and the operator would rightly not trust the button.
        """
        try:
            stored = load_lease(self.project_root)
        except (OSError, ValueError):
            return
        if not stored or stored.get("lease_id") != self.lease.get("lease_id"):
            return
        if stored.get("state") != "active":
            return
        for field in ("expires_at_epoch", "ttl_seconds", "billable_seconds", "extensions"):
            if field in stored:
                self.lease[field] = stored[field]

    def _watch(self) -> None:
        while not self._stop_event.is_set():
            self._refresh_from_disk()
            if remaining_seconds(self.lease) <= 0:
                self.log(
                    f"[lease] free quota of {self.lease['ttl_seconds']}s reached — "
                    "stopping services and deleting smoke data"
                )
                self._reason = "expired"
                self.teardown("expired")
                return
            self._stop_event.wait(0.5)

    def release(self, reason: str = "completed") -> dict[str, Any]:
        self._stop_event.set()
        return self.teardown(reason)

    # teardown -----------------------------------------------------------
    def teardown(self, reason: str) -> dict[str, Any]:
        with self._teardown_lock:
            if self._teardown_done.is_set():
                return self.teardown_report
            self._teardown_done.set()
            report: dict[str, Any] = {
                "reason": reason,
                "stopped_at": utc_now(),
                "processes": [],
                "compose": [],
                "removed_paths": [],
                "errors": [],
            }
            for process in self._processes:
                report["processes"].append(self._stop_process(process))
            for compose_file in self._compose_files:
                report["compose"].append(self._compose_down(compose_file))
            for path in self._paths:
                report["removed_paths"].append(self._remove_path(path))

            self.lease["state"] = "expired" if reason == "expired" else "released"
            self.lease["ended_at"] = utc_now()
            self.lease["end_reason"] = reason
            self.lease["teardown"] = report
            self.lease["teardown_complete"] = not report["errors"]
            save_lease(self.project_root, self.lease)
            write_json(runtime_dir(self.project_root) / LEASE_RESULT_FILE, self.lease)
            self.teardown_report = report
            return report

    def _stop_process(self, process: subprocess.Popen) -> dict[str, Any]:
        entry: dict[str, Any] = {"pid": process.pid, "graceful": False, "killed": False}
        if process.poll() is not None:
            entry["already_exited"] = True
            entry["exit_code"] = process.returncode
            return entry
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:  # pragma: no cover - windows path
                process.terminate()
        except (ProcessLookupError, PermissionError, OSError) as error:
            entry["signal_error"] = str(error)
        try:
            process.wait(timeout=self.lease.get("grace_seconds", DEFAULT_GRACE_SECONDS))
            entry["graceful"] = True
            entry["exit_code"] = process.returncode
        except subprocess.TimeoutExpired:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:  # pragma: no cover - windows path
                    process.kill()
            except (ProcessLookupError, PermissionError, OSError) as error:
                entry["kill_error"] = str(error)
            entry["killed"] = True
            try:
                process.wait(timeout=10)
                entry["exit_code"] = process.returncode
            except subprocess.TimeoutExpired:
                entry["exit_code"] = None
        return entry

    def _compose_down(self, compose_file: Path) -> dict[str, Any]:
        command = ["docker", "compose", "-f", str(compose_file), "down", "-v", "--remove-orphans"]
        if not shutil.which("docker"):
            return {"compose_file": str(compose_file), "status": "NOT_RUN", "reason": "docker not available"}
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
            if completed.returncode == 0:
                status = "ok"
            elif daemon_unreachable(completed.stderr + completed.stdout):
                # Nothing was ever started, so nothing is left behind. This is a
                # NOT_RUN, not a teardown failure — but it still never passes.
                status = "NOT_RUN"
            else:
                status = "failed"
            return {
                "compose_file": str(compose_file),
                "status": status,
                "exit_code": completed.returncode,
                "stderr_tail": completed.stderr[-2000:],
            }
        except (subprocess.TimeoutExpired, OSError) as error:
            return {"compose_file": str(compose_file), "status": "failed", "error": str(error)}

    def _remove_path(self, path: Path) -> dict[str, Any]:
        entry: dict[str, Any] = {"path": str(path)}
        try:
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=False)
                entry["removed"] = "directory"
            elif path.exists():
                path.unlink()
                entry["removed"] = "file"
            else:
                entry["removed"] = "absent"
        except OSError as error:
            entry["removed"] = "failed"
            entry["error"] = str(error)
        return entry


def _cmd_start(args: argparse.Namespace) -> int:
    lease = new_lease(Path(args.project), ttl_seconds=args.ttl, grace_seconds=args.grace, entry=args.entry)
    print(json.dumps(lease, indent=2))
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    lease = load_lease(Path(args.project))
    if not lease:
        print("no lease recorded")
        return 1
    lease["remaining_seconds"] = round(remaining_seconds(lease), 1) if lease.get("state") == "active" else 0
    print(json.dumps(lease, indent=2))
    return 0


def _cmd_extend(args: argparse.Namespace) -> int:
    lease = extend(Path(args.project), args.seconds, args.reason, args.actor)
    print(json.dumps(lease["extensions"][-1], indent=2))
    return 0


def _cmd_stop(args: argparse.Namespace) -> int:
    project = Path(args.project)
    lease = load_lease(project)
    if not lease:
        print("no lease recorded")
        return 1
    watchdog = LeaseWatchdog(project, lease)
    for entry in lease.get("managed_compose_files", []):
        watchdog.track_compose(Path(entry))
    for entry in lease.get("managed_paths", []):
        watchdog.track_path(Path(entry))
    for entry in lease.get("managed_processes", []):
        pid = entry.get("pid")
        if pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass
    report = watchdog.teardown(args.reason)
    print(json.dumps(report, indent=2))
    return 0 if not report["errors"] else 1


def main() -> int:
    if os.name == "posix" and hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # tolerate `| head`
    parser = argparse.ArgumentParser(description="Smoke runtime lease manager")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start")
    start.add_argument("--project", default=".")
    start.add_argument("--ttl", type=int, default=DEFAULT_FREE_QUOTA_SECONDS)
    start.add_argument("--grace", type=int, default=DEFAULT_GRACE_SECONDS)
    start.add_argument("--entry", default="script")
    start.set_defaults(func=_cmd_start)

    status = sub.add_parser("status")
    status.add_argument("--project", default=".")
    status.set_defaults(func=_cmd_status)

    extend_cmd = sub.add_parser("extend")
    extend_cmd.add_argument("--project", default=".")
    extend_cmd.add_argument("--seconds", type=int, required=True)
    extend_cmd.add_argument("--reason", required=True)
    extend_cmd.add_argument("--actor", required=True)
    extend_cmd.set_defaults(func=_cmd_extend)

    stop = sub.add_parser("stop")
    stop.add_argument("--project", default=".")
    stop.add_argument("--reason", default="manual")
    stop.set_defaults(func=_cmd_stop)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
