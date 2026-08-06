#!/usr/bin/env python3
"""One-click smoke runner for an ELMOS-generated or converted project.

Vendored into every pack at `smoke/tools/run_smoke.py`, stdlib only, so the user
can clone the generated project and run it with a single command:

    ./run-smoke.sh

What it does, in order: allocate a port, load the disposable seed data, start
the declared entry, wait for readiness, run the functional smoke assertions,
hold the service for the free runtime lease, then stop everything and delete the
smoke data when the lease expires.

Exit codes:
    0  every required assertion passed and teardown completed
    1  a required assertion failed
    3  the pack is not runnable as configured (missing entry, missing files)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_common import (  # noqa: E402
    DEFAULT_FREE_QUOTA_SECONDS,
    DEFAULT_GRACE_SECONDS,
    SCHEMA_PREFIX,
    TRISTATE_FAIL,
    TRISTATE_NOT_RUN,
    TRISTATE_PASS,
    canonical_digest,
    daemon_unreachable,
    free_port,
    port_open,
    read_json,
    smoke_dir,
    utc_now,
    wait_for_port,
    write_json,
)
from smoke_lease import LeaseWatchdog, new_lease, remaining_seconds, runtime_dir  # noqa: E402

HOST = "127.0.0.1"


def log(message: str) -> None:
    print(message, flush=True)


def load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.is_file():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def http_probe(url: str, method: str = "GET", timeout: float = 5.0) -> tuple[int | None, str, str | None]:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": "elmos-smoke/1"})
    if method in ("POST", "PUT", "PATCH"):
        request.data = b"{}"
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return response.status, body, None
    except urllib.error.HTTPError as error:
        body = error.read(4096).decode("utf-8", errors="replace") if error.fp else ""
        return error.code, body, None
    except (urllib.error.URLError, OSError, ValueError) as error:
        return None, "", str(error)


class SmokeRun:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.root = Path(args.project).resolve()
        self.smoke = smoke_dir(self.root)
        self.profile = self._require("profile.json")
        self.requirements = self._require("minimal-data-requirements.json")
        self.assertions = self._require("assertions.json")
        self.manifest = self._require("runner-manifest.json")
        self.stacks = self.profile.get("stacks", [])
        self.primary = next((s for s in self.stacks if s.get("role") == "primary"),
                            self.stacks[0] if self.stacks else {})
        self.entry = args.entry or self.manifest.get("default_entry") or "script"
        self.port = 0
        self.results: list[dict[str, Any]] = []
        self.process: subprocess.Popen | None = None
        self.logs_dir = runtime_dir(self.root) / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.stdout_path = self.logs_dir / "app.stdout.log"
        self.stderr_path = self.logs_dir / "app.stderr.log"
        self.lease = new_lease(self.root, ttl_seconds=args.ttl, grace_seconds=args.grace, entry=self.entry)
        self.watchdog = LeaseWatchdog(self.root, self.lease, log=log)
        self.notes: list[str] = []
        self._state = "STARTING"

    def _require(self, name: str) -> dict[str, Any]:
        path = self.smoke / name
        if not path.is_file():
            log(f"run-smoke: missing {path.relative_to(self.root)}; regenerate the smoke pack")
            raise SystemExit(3)
        return read_json(path)

    # ---------------------------------------------------------------- status
    def publish(self, state: str | None = None) -> None:
        """Write a live status file a console or IDE can poll while the run is up.

        `result.json` only exists once the run is over, so anything that wants to
        show a countdown or a link while the service is live reads this instead.
        """
        if state:
            self._state = state
        state = self._state
        payload = {
            "schema": f"{SCHEMA_PREFIX}.smoke-status/1",
            "state": state,
            "updated_at": utc_now(),
            "lease_id": self.lease["lease_id"],
            "entry": self.entry,
            "port": self.port or None,
            "url": f"http://{HOST}:{self.port}" if self.port else None,
            "free_quota_seconds": self.lease["free_quota_seconds"],
            "ttl_seconds": self.lease["ttl_seconds"],
            "billable_seconds": self.lease["billable_seconds"],
            "expires_at_epoch": self.lease["expires_at_epoch"],
            "remaining_seconds": round(remaining_seconds(self.lease), 1)
            if state in ("STARTING", "READY", "HOLDING") else 0,
            "checks": [
                {"id": item["id"], "status": item["status"], "detail": item["detail"],
                 "required": item["required"]}
                for item in self.results
            ],
            "notes": self.notes,
        }
        write_json(runtime_dir(self.root) / "status.json", payload)

    # ---------------------------------------------------------------- record
    def record(self, check_id: str, status: str, detail: str, required: bool, **extra: Any) -> None:
        self.results.append({
            "id": check_id,
            "status": status,
            "required": required,
            "detail": detail,
            "observed_at": utc_now(),
            **extra,
        })
        marker = {TRISTATE_PASS: "PASS", TRISTATE_FAIL: "FAIL", TRISTATE_NOT_RUN: "NOT_RUN"}.get(status, status)
        log(f"[{marker:>7}] {check_id}: {detail}")
        self.publish()

    def check(self, check_id: str) -> dict[str, Any]:
        for item in self.assertions.get("checks", []):
            if item["id"] == check_id:
                return item
        return {}

    # ------------------------------------------------------------ environment
    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        env.update(load_env_file(self.smoke / "seed" / "env.smoke"))
        self.port = free_port(self.primary.get("default_port") or None)
        env["SMOKE_PORT"] = str(self.port)
        env["PORT"] = str(self.port)
        env["SMOKE_MODE"] = "1"
        env["SMOKE_LEASE_ID"] = self.lease["lease_id"]
        if self.entry == "zero-dep":
            env.update(self.prepare_zero_dep())
        env.update(self.runtime_overrides(env))
        return env

    def runtime_overrides(self, env: dict[str, str]) -> dict[str, str]:
        """Point connection-shaped variables at the topology this entry started."""
        path = self.smoke / "seed" / "runtime-overrides.json"
        if not path.is_file():
            return {}
        overrides = read_json(path).get("by_entry", {}).get(self.entry, {})
        resolved: dict[str, str] = {}
        for name, value in overrides.items():
            expanded = value.replace("${SMOKE_SQLITE_PATH}", env.get("SMOKE_SQLITE_PATH", ""))
            if "${" in expanded:
                self.notes.append(f"runtime override for {name} left unexpanded: {value}")
                continue
            resolved[name] = expanded
        if resolved:
            log(f"[  info ] runtime overrides applied for entry '{self.entry}': {', '.join(sorted(resolved))}")
        return resolved

    def prepare_zero_dep(self) -> dict[str, str]:
        db_path = runtime_dir(self.root) / "smoke.sqlite"
        if db_path.exists():
            db_path.unlink()
        self.watchdog.track_path(db_path)
        applied = 0
        failed: list[str] = []
        schema_files = sorted({d["source_file"] for d in self.requirements.get("datasets", [])
                               if d.get("source_file")})
        seed_sql = self.smoke / "seed" / "seed.sql"
        try:
            connection = sqlite3.connect(db_path)
            for rel_path in schema_files:
                path = self.root / rel_path
                if not path.is_file():
                    continue
                try:
                    connection.executescript(path.read_text(encoding="utf-8"))
                    applied += 1
                except sqlite3.Error as error:
                    failed.append(f"{rel_path}: {error}")
            if seed_sql.is_file():
                try:
                    connection.executescript(seed_sql.read_text(encoding="utf-8"))
                except sqlite3.Error as error:
                    failed.append(f"smoke/seed/seed.sql: {error}")
            connection.commit()
            connection.close()
        except sqlite3.Error as error:
            failed.append(str(error))
        if failed:
            self.notes.append(
                "zero-dep substitution could not load the declared schema verbatim: " + "; ".join(failed[:3])
            )
        log(f"[  info ] zero-dep: sqlite at {db_path.name}, {applied} schema file(s) applied, {len(failed)} error(s)")
        return {
            "DATABASE_URL": f"sqlite:///{db_path}",
            "SMOKE_SQLITE_PATH": str(db_path),
            "SMOKE_ZERO_DEP": "1",
        }

    # ----------------------------------------------------------------- start
    def start_compose(self) -> bool:
        compose_file = self.root / "docker-compose.smoke.yml"
        if not compose_file.is_file():
            self.record("process-started", TRISTATE_NOT_RUN,
                        "compose entry requested but docker-compose.smoke.yml is absent", True)
            return False
        if not shutil.which("docker"):
            self.record("process-started", TRISTATE_NOT_RUN,
                        "compose entry requested but docker is not installed on this machine", True)
            return False
        self.watchdog.track_compose(compose_file)
        completed = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "up", "-d", "--wait"],
            cwd=self.root, capture_output=True, text=True, timeout=self.args.startup_timeout,
        )
        (self.logs_dir / "compose.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode != 0:
            unreachable = daemon_unreachable(completed.stderr + completed.stdout)
            self.record(
                "process-started",
                TRISTATE_NOT_RUN if unreachable else TRISTATE_FAIL,
                "the docker daemon is not reachable on this machine; the compose entry cannot run here"
                if unreachable else f"docker compose up failed with exit {completed.returncode}",
                True,
                stderr_tail=completed.stderr[-2000:],
            )
            return False
        return True

    def start_process(self, env: dict[str, str]) -> bool:
        command = self.primary.get("start_command")
        if not command:
            self.record("process-started", TRISTATE_NOT_RUN,
                        "no start command declared for the primary stack", True)
            return False
        command = command.replace("${SMOKE_PORT}", str(self.port))
        if self.args.install and self.primary.get("install_command"):
            install = self.primary["install_command"]
            log(f"[  info ] installing dependencies: {install}")
            installed = subprocess.run(install, shell=True, cwd=self.root, env=env,
                                       capture_output=True, text=True, timeout=self.args.install_timeout)
            (self.logs_dir / "install.log").write_text(installed.stdout + installed.stderr, encoding="utf-8")
            if installed.returncode != 0:
                self.record("process-started", TRISTATE_FAIL,
                            f"dependency install failed with exit {installed.returncode}", True,
                            stderr_tail=installed.stderr[-2000:])
                return False
        log(f"[  info ] starting: {command}")
        stdout = self.stdout_path.open("w", encoding="utf-8")
        stderr = self.stderr_path.open("w", encoding="utf-8")
        popen_kwargs: dict[str, Any] = {
            "cwd": self.root, "env": env, "stdout": stdout, "stderr": stderr, "shell": True,
        }
        if os.name == "posix":
            popen_kwargs["preexec_fn"] = os.setsid
        self.process = subprocess.Popen(command, **popen_kwargs)
        self.watchdog.track_process(self.process, label=self.primary.get("id", "primary"))
        time.sleep(0.4)
        if self.process.poll() is not None:
            self.record("process-started", TRISTATE_FAIL,
                        f"start command exited immediately with code {self.process.returncode}", True,
                        stderr_tail=self.stderr_path.read_text(encoding='utf-8', errors='replace')[-2000:])
            return False
        self.record("process-started", TRISTATE_PASS, f"pid {self.process.pid} is live", True)
        return True

    # ------------------------------------------------------------ assertions
    def assert_port(self) -> bool:
        spec = self.check("port-listening")
        if not spec.get("required"):
            self.record("port-listening", TRISTATE_NOT_RUN, "no listen port declared for this stack", False)
            return True
        timeout = float(spec.get("timeout_seconds", 120))
        if wait_for_port(HOST, self.port, timeout=timeout):
            self.record("port-listening", TRISTATE_PASS, f"{HOST}:{self.port} accepted a connection", True,
                        port=self.port)
            return True
        self.record("port-listening", TRISTATE_FAIL,
                    f"nothing listening on {HOST}:{self.port} after {timeout:.0f}s", True, port=self.port,
                    stderr_tail=self.stderr_path.read_text(encoding='utf-8', errors='replace')[-2000:]
                    if self.stderr_path.is_file() else "")
        return False

    def assert_http(self, check_id: str) -> None:
        spec = self.check(check_id)
        if not spec:
            return
        if not spec.get("required"):
            self.record(check_id, TRISTATE_NOT_RUN, spec.get("expect", "not applicable"), False)
            return
        url = f"http://{HOST}:{self.port}{spec.get('path', '/')}"
        deadline = time.time() + float(spec.get("timeout_seconds", 30))
        status = None
        body = ""
        error = None
        while time.time() < deadline:
            status, body, error = http_probe(url, spec.get("method", "GET"))
            if status is not None:
                break
            time.sleep(0.5)
        accept = spec.get("accept_status", [200])
        if status is None:
            self.record(check_id, TRISTATE_FAIL, f"{url} did not answer ({error})", True, url=url)
        elif status in accept:
            self.record(check_id, TRISTATE_PASS, f"{url} -> {status}", True, url=url,
                        http_status=status, body_head=body[:200])
        else:
            self.record(check_id, TRISTATE_FAIL, f"{url} -> {status}, expected one of {accept}", True,
                        url=url, http_status=status, body_head=body[:200])

    def assert_seed_visible(self) -> None:
        spec = self.check("seed-visible")
        if not spec:
            return
        db_path = runtime_dir(self.root) / "smoke.sqlite"
        if self.entry != "zero-dep" or not db_path.is_file():
            self.record("seed-visible", TRISTATE_NOT_RUN,
                        "seed visibility is only directly observable through the zero-dep datastore; "
                        "for compose and script entries assert it through a functional endpoint", False)
            return
        tables = [d["table"].split(".")[-1] for d in self.requirements.get("datasets", []) if d.get("table")]
        counted: dict[str, int] = {}
        try:
            connection = sqlite3.connect(db_path)
            for table in tables:
                try:
                    counted[table] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                except sqlite3.Error:
                    counted[table] = -1
            connection.close()
        except sqlite3.Error as error:
            self.record("seed-visible", TRISTATE_FAIL, f"could not read the ephemeral datastore: {error}", False)
            return
        seeded = {t: c for t, c in counted.items() if c > 0}
        if seeded and len(seeded) == len(counted):
            self.record("seed-visible", TRISTATE_PASS,
                        f"{len(seeded)} table(s) hold seeded rows: {json.dumps(seeded)}", False, rows=counted)
        elif seeded:
            self.record("seed-visible", TRISTATE_FAIL,
                        f"only {len(seeded)}/{len(counted)} declared tables hold rows: {json.dumps(counted)}",
                        False, rows=counted)
        else:
            self.record("seed-visible", TRISTATE_FAIL, "no seeded rows are readable", False, rows=counted)

    # ------------------------------------------------------------------ hold
    def hold(self) -> None:
        if self.args.no_hold:
            log("[  info ] --no-hold: asserting and tearing down immediately")
            return
        total = int(self.lease["ttl_seconds"])
        log(
            f"\n[  info ] service is up on http://{HOST}:{self.port} — free runtime lease of "
            f"{total // 60}m{total % 60:02d}s is running."
        )
        log("[  info ] press Ctrl-C to stop early; everything is removed automatically when the lease expires.")
        announced: set[int] = set()
        milestones = (300, 120, 60, 30, 10)
        try:
            while remaining_seconds(self.lease) > 0:
                left = int(remaining_seconds(self.lease))
                for milestone in milestones:
                    if left == milestone and milestone not in announced:
                        announced.add(milestone)
                        log(f"[  info ] {left}s of free runtime remaining")
                        break
                if self.process is not None and self.process.poll() is not None:
                    log(f"[  warn ] the application exited on its own with code {self.process.returncode}")
                    return
                time.sleep(1)
        except KeyboardInterrupt:
            log("\n[  info ] interrupted — releasing the lease early")

    def assert_shutdown(self, report: dict[str, Any], reason: str) -> None:
        entries = report.get("processes", [])
        if not entries:
            self.record("graceful-shutdown", TRISTATE_NOT_RUN,
                        "no host process was started by this entry", True)
        else:
            killed = [e for e in entries if e.get("killed")]
            if killed:
                self.record("graceful-shutdown", TRISTATE_FAIL,
                            f"{len(killed)} process(es) ignored SIGTERM and were killed after the grace period",
                            True, processes=entries)
            else:
                self.record("graceful-shutdown", TRISTATE_PASS,
                            "every process exited within the grace period after SIGTERM", True, processes=entries)
        residual = [e for e in entries if e.get("exit_code") is None and not e.get("already_exited")]
        removed = report.get("removed_paths", [])
        remove_failures = [e for e in removed if e.get("removed") == "failed"]
        compose_failures = [e for e in report.get("compose", []) if e.get("status") == "failed"]
        listening = port_open(HOST, self.port, timeout=0.4) if self.port else False
        if residual or remove_failures or compose_failures or listening:
            self.record("lease-teardown", TRISTATE_FAIL,
                        "teardown left residue: "
                        f"{len(residual)} live process(es), {len(remove_failures)} undeleted path(s), "
                        f"{len(compose_failures)} compose failure(s), port_still_listening={listening}",
                        True, teardown=report)
        else:
            self.record("lease-teardown", TRISTATE_PASS,
                        f"lease {reason}: services stopped, containers and volumes removed, "
                        f"{len(removed)} ephemeral path(s) deleted", True, teardown=report)

    # ---------------------------------------------------------------- evidence
    def write_evidence(self, reason: str) -> dict[str, Any]:
        required = [r for r in self.results if r["required"]]
        failed = [r for r in required if r["status"] != TRISTATE_PASS]
        not_run = [r for r in required if r["status"] == TRISTATE_NOT_RUN]
        overall = TRISTATE_PASS if not failed else (
            TRISTATE_NOT_RUN if len(not_run) == len(failed) else TRISTATE_FAIL
        )
        result = {
            "schema": f"{SCHEMA_PREFIX}.smoke-result/1",
            "generated_at": utc_now(),
            "lease_id": self.lease["lease_id"],
            "entry": self.entry,
            "port": self.port,
            "overall": overall,
            "required_total": len(required),
            "required_passed": len(required) - len(failed),
            "checks": self.results,
            "notes": self.notes,
            "environment_manifest": {
                "platform": sys.platform,
                "python": sys.version.split()[0],
                "docker": bool(shutil.which("docker")),
                "node": bool(shutil.which("node")),
                "java": bool(shutil.which("java")),
                "dotnet": bool(shutil.which("dotnet")),
                "cwd": str(self.root),
            },
            "lease": {
                "free_quota_seconds": self.lease["free_quota_seconds"],
                "ttl_seconds": self.lease["ttl_seconds"],
                "billable_seconds": self.lease["billable_seconds"],
                "end_reason": reason,
                "teardown_complete": self.lease.get("teardown_complete"),
            },
            "raw_logs": {
                "stdout": "smoke/runtime/logs/app.stdout.log",
                "stderr": "smoke/runtime/logs/app.stderr.log",
            },
            "scope_disclaimer": (
                "Functional smoke evidence only. This result never substitutes for route, framework, "
                "database, client or certification gates."
            ),
        }
        result["result_digest"] = canonical_digest(
            {k: v for k, v in result.items() if k not in ("generated_at", "result_digest")}
        )
        write_json(runtime_dir(self.root) / "result.json", result)
        return result

    # -------------------------------------------------------------------- run
    def execute(self) -> int:
        log(f"ELMOS smoke run — entry '{self.entry}', lease {self.lease['ttl_seconds']}s, project {self.root.name}")
        entry_state = self.manifest.get("entries", {}).get(self.entry, {})
        if entry_state.get("status") != "available":
            log(f"run-smoke: entry '{self.entry}' is unavailable: {entry_state.get('reason', 'unknown reason')}")
            available = [n for n, e in self.manifest.get("entries", {}).items() if e.get("status") == "available"]
            log(f"run-smoke: available entries: {', '.join(available) or 'none'}")
            return 3
        if entry_state.get("semantic_warning"):
            log(f"[  warn ] {entry_state['semantic_warning']}")
            self.notes.append(entry_state["semantic_warning"])

        self.watchdog.start()
        started = True
        env = self.build_env()
        self.publish("STARTING")
        try:
            if self.entry == "compose":
                started = self.start_compose()
                if started and not entry_state.get("app_runs_in_container"):
                    started = self.start_process(env)
                elif started:
                    self.record("process-started", TRISTATE_PASS, "compose services are up and healthy", True)
            else:
                started = self.start_process(env)

            if started:
                if self.assert_port():
                    self.assert_http("http-readiness")
                    self.assert_http("http-functional")
                else:
                    self.record("http-readiness", TRISTATE_NOT_RUN, "port never opened", True)
                    self.record("http-functional", TRISTATE_NOT_RUN, "port never opened",
                                bool(self.check("http-functional").get("required")))
                self.assert_seed_visible()
                if all(r["status"] == TRISTATE_PASS for r in self.results if r["required"]):
                    self.publish("HOLDING")
                    self.hold()
        finally:
            reason = "expired" if remaining_seconds(self.lease) <= 0 else "completed"
            report = self.watchdog.release(reason)
            self.assert_shutdown(report, reason)
            result = self.write_evidence(reason)
            self.publish("EXPIRED" if reason == "expired" else
                         "COMPLETED" if result["overall"] == TRISTATE_PASS else "FAILED")

        log("")
        log(f"smoke result: {result['overall']} "
            f"({result['required_passed']}/{result['required_total']} required checks passed)")
        log(f"evidence: smoke/runtime/result.json  ·  lease: smoke/runtime/lease-result.json")
        if result["overall"] == TRISTATE_PASS:
            return 0
        if result["overall"] == TRISTATE_NOT_RUN:
            return 3
        return 1


def main() -> int:
    if os.name == "posix" and hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # tolerate `| head`
    parser = argparse.ArgumentParser(description="Run the one-click smoke test for this project")
    parser.add_argument("--project", default=".")
    parser.add_argument("--entry", choices=["script", "compose", "make", "zero-dep"])
    parser.add_argument("--ttl", type=int, default=DEFAULT_FREE_QUOTA_SECONDS,
                        help="runtime lease in seconds (default: the 10 minute free quota)")
    parser.add_argument("--grace", type=int, default=DEFAULT_GRACE_SECONDS)
    parser.add_argument("--no-hold", action="store_true",
                        help="assert and tear down immediately instead of holding the service for the lease")
    parser.add_argument("--seed-only", action="store_true", help="print the seed manifest and exit")
    parser.add_argument("--no-install", dest="install", action="store_false", default=True)
    parser.add_argument("--install-timeout", type=int, default=900)
    parser.add_argument("--startup-timeout", type=int, default=300)
    args = parser.parse_args()

    if args.seed_only:
        manifest_path = smoke_dir(Path(args.project)) / "seed-manifest.json"
        if not manifest_path.is_file():
            print("no seed manifest; regenerate the smoke pack")
            return 3
        print(json.dumps(read_json(manifest_path), indent=2, ensure_ascii=False))
        return 0

    run = SmokeRun(args)

    def _signal_handler(signum, _frame):  # pragma: no cover - interactive path
        log(f"\n[  info ] signal {signum} received — releasing the lease")
        run.watchdog.release("signal")
        raise SystemExit(1)

    if os.name == "posix":
        signal.signal(signal.SIGTERM, _signal_handler)
    return run.execute()


if __name__ == "__main__":
    raise SystemExit(main())
