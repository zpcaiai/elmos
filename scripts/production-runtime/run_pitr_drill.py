#!/usr/bin/env python3
"""Run a disposable PostgreSQL WAL/PITR drill without executing package code.

The drill creates two explicitly named disposable containers, takes a physical
base backup, replays WAL to a target LSN, and proves that a post-target row is
not present. It is local engineering evidence only; it does not certify any
hosted backup provider or production database.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path


class DrillError(RuntimeError):
    pass


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["docker", *args], text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise DrillError(
            f"docker {' '.join(args)} failed with {result.returncode}: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def wait_ready(container: str, database: str = "postgres", timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        result = docker("exec", container, "pg_isready", "-U", "postgres", "-d", database, check=False)
        if result.returncode == 0:
            probe = docker(
                "exec",
                container,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "postgres",
                "-d",
                database,
                "-At",
                "-c",
                "select 1",
                check=False,
            )
            if probe.returncode == 0 and probe.stdout.strip() == "1":
                return
        time.sleep(0.5)
    logs = docker("logs", container, check=False)
    raise DrillError(f"container {container} did not become ready: {logs.stdout[-4000:]}")


def psql(container: str, statement: str, database: str = "runtime") -> str:
    return docker(
        "exec", container, "psql", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", database, "-At", "-c", statement
    ).stdout.strip()


def ensure_database(container: str, database: str) -> None:
    """Make the drill independent of image entrypoint database initialization."""
    deadline = time.monotonic() + 45.0
    last_error = "database initialization did not settle"
    while time.monotonic() < deadline:
        result = docker(
            "exec",
            container,
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-At",
            "-c",
            f"select 1 from pg_database where datname = '{database}'",
            check=False,
        )
        if result.returncode == 0:
            if result.stdout.strip() != "1":
                create = docker(
                    "exec",
                    container,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                    "-At",
                    "-c",
                    f"create database {database}",
                    check=False,
                )
                if create.returncode != 0:
                    last_error = create.stderr.strip() or create.stdout.strip()
                    time.sleep(0.5)
                    continue
            return
        last_error = result.stderr.strip() or result.stdout.strip()
        time.sleep(0.5)
    raise DrillError(f"could not establish database {database}: {last_error}")


def wait_for_archives(archive_dir: Path, timeout_seconds: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if any(path.is_file() for path in archive_dir.iterdir()):
            return
        time.sleep(0.5)
    raise DrillError("primary did not archive a WAL segment")


def prepare_base_backup(container: str) -> None:
    docker(
        "exec",
        "-e",
        "PGPASSWORD=postgres",
        container,
        "pg_basebackup",
        "-h",
        "127.0.0.1",
        "-U",
        "postgres",
        "-D",
        "/var/lib/postgresql/base_backup",
        "-Fp",
        "-Xs",
        "-P",
    )


def run(output: Path | None) -> dict[str, object]:
    run_id = str(uuid.uuid4())
    suffix = uuid.uuid4().hex[:12]
    primary = f"elmos-pitr-primary-{suffix}"
    restored = f"elmos-pitr-restored-{suffix}"
    temp_root = Path(tempfile.mkdtemp(prefix="elmos-production-runtime-pitr-"))
    archive_dir = temp_root / "wal_archive"
    base_dir = temp_root / "base_backup"
    archive_dir.mkdir(mode=0o777)
    base_dir.mkdir(mode=0o777)
    # The PostgreSQL image writes the mounted WAL and base-backup directories
    # as its non-root postgres user. These are disposable, explicit paths.
    archive_dir.chmod(0o777)
    base_dir.chmod(0o777)
    markers = {
        "base": f"base-{run_id}",
        "target": f"target-{run_id}",
        "post_target": f"post-target-{run_id}",
    }
    try:
        docker(
            "run",
            "-d",
            "--name",
            primary,
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-e",
            "POSTGRES_DB=runtime",
            "-v",
            f"{archive_dir}:/var/lib/postgresql/wal_archive",
            "-v",
            f"{base_dir}:/var/lib/postgresql/base_backup",
            "postgres:17.5-alpine",
            "postgres",
            "-c",
            "wal_level=replica",
            "-c",
            "archive_mode=on",
            "-c",
            "archive_timeout=1s",
            "-c",
            "max_wal_senders=2",
            "-c",
            "archive_command=test ! -f /var/lib/postgresql/wal_archive/%f && cp %p /var/lib/postgresql/wal_archive/%f",
        )
        # pg_isready can report a healthy server even when the requested
        # database was not created by an image entrypoint. Wait for the
        # maintenance database first, then establish the drill database.
        wait_ready(primary, database="postgres")
        ensure_database(primary, "runtime")
        wait_ready(primary, database="runtime")
        psql(primary, "create table pitr_probe (marker text primary key, created_at timestamptz not null default now())")
        psql(primary, f"insert into pitr_probe(marker) values ('{markers['base']}')")
        prepare_base_backup(primary)

        psql(primary, f"insert into pitr_probe(marker) values ('{markers['target']}')")
        target_lsn = psql(primary, "select pg_current_wal_lsn()")
        psql(primary, "select pg_switch_wal()")
        wait_for_archives(archive_dir)
        psql(primary, f"insert into pitr_probe(marker) values ('{markers['post_target']}')")
        psql(primary, "select pg_switch_wal()")
        wait_for_archives(archive_dir)

        (base_dir / "recovery.signal").touch()
        (base_dir / "postgresql.auto.conf").write_text(
            "restore_command = 'cp /var/lib/postgresql/wal_archive/%f %p'\n"
            f"recovery_target_lsn = '{target_lsn}'\n"
            "recovery_target_action = 'promote'\n",
            encoding="utf-8",
        )
        docker(
            "run",
            "-d",
            "--name",
            restored,
            "-e",
            "POSTGRES_PASSWORD=postgres",
            "-v",
            f"{base_dir}:/var/lib/postgresql/data",
            "-v",
            f"{archive_dir}:/var/lib/postgresql/wal_archive",
            "postgres:17.5-alpine",
            "postgres",
            "-c",
            "port=5432",
        )
        wait_ready(restored)
        rows = set(filter(None, psql(restored, "select marker from pitr_probe order by marker").splitlines()))
        expected = {markers["base"], markers["target"]}
        if not expected.issubset(rows):
            raise DrillError(f"PITR restore lost expected rows: expected={sorted(expected)}, observed={sorted(rows)}")
        if markers["post_target"] in rows:
            raise DrillError("PITR restore replayed data after the declared target LSN")
        report = {
            "status": "LOCAL_HARNESS_PASS",
            "scenario": "PITRRestore",
            "execution_kind": "LOCAL_DISPOSABLE_POSTGRES_WAL_REPLAY",
            "test_run_id": run_id,
            "postgres_image": "postgres:17.5-alpine",
            "target_lsn": target_lsn,
            "markers": markers,
            "observed_rows": sorted(rows),
            "production_certification": "NOT_CERTIFIED",
        }
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
    finally:
        docker("rm", "-f", primary, check=False)
        docker("rm", "-f", restored, check=False)
        shutil.rmtree(temp_root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run(args.output)
    except (DrillError, OSError, subprocess.SubprocessError) as exc:
        print(f"production-runtime PITR drill: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
