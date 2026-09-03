#!/usr/bin/env python3
"""Run build-cache PostgreSQL qualification in a disposable local cluster.

The tool never accepts an external DSN.  It creates its own cluster below
``/tmp``, exposes PostgreSQL only through a mode-0700 Unix socket, leaves
``fsync`` and ``synchronous_commit`` enabled, and removes the database files
after a fast, waited-for shutdown.  The retained output directory contains
only redacted, content-addressed local engineering evidence.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ENGINE_ROOT = Path(__file__).resolve().parents[1]
TMP_ALIAS = Path(os.sep) / "tmp"
TMP_ROOT = TMP_ALIAS.resolve()
DEFAULT_POSTGRES_BIN = Path("/opt/homebrew/opt/postgresql@17/bin")
METADATA_TEST_FILE = "tests/test_metadata_store_contract.py"
SLO_TEST_FILE = "tests/test_slo_service.py"
DATABASE_NAME = "elmos_cache_qualification"
DATABASE_USER = "elmos_qualification"
CONFIRMATION = "I_CONFIRM_DISPOSABLE_LOCAL_POSTGRES_ONLY"
RECEIPT_KIND = "elmos.build-cache.local-postgres-qualification-receipt/v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return _sha256_bytes(encoded)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_environment(home: Path | None = None) -> dict[str, str]:
    isolated_home = (home or TMP_ROOT).resolve()
    temporary = isolated_home / "tmp" if home is not None else TMP_ROOT
    if home is not None:
        isolated_home.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary.mkdir(mode=0o700, exist_ok=True)
    environment = {
        "HOME": str(isolated_home),
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", os.defpath),
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(temporary),
    }
    virtual_environment = os.environ.get("VIRTUAL_ENV")
    if virtual_environment:
        environment["VIRTUAL_ENV"] = virtual_environment
    return environment


def _redact(text: str, *exact_values: str) -> str:
    redacted = text
    for value in exact_values:
        if value:
            redacted = redacted.replace(value, "[REDACTED_LOCAL_RUNTIME]")
    redacted = re.sub(
        r"(?i)postgres(?:ql)?://[^\s'\"]+",
        "[REDACTED_POSTGRES_DSN]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\b(?:password|passwd|pwd|token|secret)=([^\s]+)",
        lambda match: match.group(0).split("=", 1)[0] + "=[REDACTED]",
        redacted,
    )
    redacted = re.sub(
        r"(?i)\bhost=/[^\s'\"]+",
        "host=[REDACTED_SOCKET_DIRECTORY]",
        redacted,
    )
    return redacted


def _run(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=cwd,
        env=_safe_environment() if env is None else env,
        text=True,
        capture_output=True,
        check=False,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
    )


def _must_run(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    completed = _run(argv, cwd=cwd, env=env, timeout=timeout)
    if completed.returncode != 0:
        detail = _redact((completed.stderr or completed.stdout)[-4_000:])
        raise RuntimeError(f"COMMAND_FAILED:{Path(argv[0]).name}:{detail}")
    return completed


def _validated_tmp_parent(raw: Path, *, create: bool = False) -> Path:
    resolved = raw.expanduser().resolve()
    # macOS intentionally exposes /tmp as a system symlink to /private/tmp.
    # Permit that one canonical alias, but reject a caller-controlled symlink
    # even when its eventual target happens to be below the temporary root.
    if raw.exists() and raw.is_symlink() and raw != TMP_ALIAS:
        raise ValueError("output parent cannot be a symlink")
    if resolved != TMP_ROOT and TMP_ROOT not in resolved.parents:
        raise ValueError("output parent must resolve below /tmp")
    if create:
        resolved.mkdir(parents=True, exist_ok=True, mode=0o700)
    return resolved


def _validate_selector(selector: str, expected_file: str) -> str:
    if not selector or any(character in selector for character in ("\x00", "\n", "\r")):
        raise ValueError("pytest selector is empty or contains a control character")
    file_part = selector.split("::", 1)[0]
    if file_part != expected_file:
        raise ValueError(f"selector must target {expected_file}")
    node_parts = selector.split("::")[1:]
    if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[[A-Za-z0-9_.-]+\])?", part) for part in node_parts):
        raise ValueError("pytest node selectors may contain only identifier-safe test names")
    resolved = (ENGINE_ROOT / file_part).resolve()
    if ENGINE_ROOT not in resolved.parents or not resolved.is_file():
        raise ValueError(f"pytest selector does not resolve to a checked-in test file: {selector}")
    return selector


def _validate_public_identifier(name: str, value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@/+\-]{0,191}", value):
        raise ValueError(f"{name} must be a bounded public identifier")
    lowered = value.lower()
    if any(marker in lowered for marker in ("password", "secret", "token", "dsn=")):
        raise ValueError(f"{name} cannot contain secret-like material")
    return value


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _required_binaries(directory: Path) -> dict[str, Path]:
    resolved = directory.expanduser().resolve()
    required: dict[str, Path] = {}
    for name in ("createdb", "initdb", "pg_ctl", "postgres", "psql"):
        path = resolved / name
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"REQUIRED_POSTGRES_BINARY_MISSING:{path}")
        required[name] = path
    return required


def _required_command(name: str, environment: dict[str, str]) -> Path:
    resolved = shutil.which(name, path=environment["PATH"])
    if resolved is None:
        raise RuntimeError(f"REQUIRED_COMMAND_MISSING:{name}")
    return Path(resolved).resolve()


def _git_source_state(*, environment: dict[str, str]) -> dict[str, Any]:
    git = _required_command("git", environment)
    revision = _must_run(
        [str(git), "-C", str(ENGINE_ROOT), "rev-parse", "HEAD"],
        cwd=ENGINE_ROOT,
        env=environment,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise RuntimeError("GIT_HEAD_INVALID")
    status = _must_run(
        [
            str(git),
            "-C",
            str(ENGINE_ROOT),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        cwd=ENGINE_ROOT,
        env=environment,
    ).stdout
    return {
        "revision": revision,
        "dirty": bool(status.strip()),
    }


def _command_version(
    name: str,
    *,
    environment: dict[str, str],
    cwd: Path,
) -> str:
    command = _required_command(name, environment)
    return _must_run([str(command), "--version"], cwd=cwd, env=environment).stdout.strip()


@dataclass
class TeardownState:
    postgres_stopped: bool = False
    stop_exit_code: int | None = None
    data_directory_removed: bool = False
    socket_directory_removed: bool = False
    temporary_home_removed: bool = False

    @property
    def status(self) -> str:
        if (
            self.postgres_stopped
            and self.data_directory_removed
            and self.socket_directory_removed
            and self.temporary_home_removed
        ):
            return "COMPLETE"
        return "INCOMPLETE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "postgres_stopped": self.postgres_stopped,
            "stop_exit_code": self.stop_exit_code,
            "data_directory_removed": self.data_directory_removed,
            "socket_directory_removed": self.socket_directory_removed,
            "temporary_home_removed": self.temporary_home_removed,
        }


class DisposablePostgres:
    """One socket-only PostgreSQL cluster owned by one qualification run."""

    def __init__(self, binaries: dict[str, Path], output_parent: Path) -> None:
        self.binaries = binaries
        self.root = Path(tempfile.mkdtemp(prefix="elmos-bc-pg-qualification-", dir=str(output_parent))).resolve()
        if self.root.parent != output_parent or not self.root.name.startswith("elmos-bc-pg-qualification-"):
            raise RuntimeError("UNSAFE_QUALIFICATION_ROOT")
        self.root.chmod(0o700)
        self.data_directory = self.root / "postgres-data"
        self.socket_directory = self.root / "socket"
        self.home_directory = self.root / "home"
        self.server_log = self.root / "postgres-server.log"
        self.port = _free_loopback_port()
        self.started = False
        self.ever_started = False
        self.teardown = TeardownState()
        self._atexit_registered = False
        self.process_environment = _safe_environment(self.home_directory)

    @property
    def dsn(self) -> str:
        return f"host={self.socket_directory} port={self.port} dbname={DATABASE_NAME} user={DATABASE_USER}"

    def __enter__(self) -> DisposablePostgres:
        self.socket_directory.mkdir(mode=0o700)
        try:
            _must_run(
                [
                    str(self.binaries["initdb"]),
                    "--pgdata",
                    str(self.data_directory),
                    "--auth-local=trust",
                    "--auth-host=reject",
                    "--encoding=UTF8",
                    "--no-locale",
                    f"--username={DATABASE_USER}",
                ],
                cwd=self.root,
                env=self.process_environment,
            )
            configuration = self.data_directory / "postgresql.conf"
            with configuration.open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n# ELMOS disposable build-cache qualification\n"
                    "listen_addresses = ''\n"
                    f"port = {self.port}\n"
                    f"unix_socket_directories = '{self.socket_directory}'\n"
                    "unix_socket_permissions = 0700\n"
                    "fsync = on\n"
                    "synchronous_commit = on\n"
                    "full_page_writes = on\n"
                )
            _must_run(
                [
                    str(self.binaries["pg_ctl"]),
                    "-D",
                    str(self.data_directory),
                    "-l",
                    str(self.server_log),
                    "-w",
                    "start",
                ],
                cwd=self.root,
                env=self.process_environment,
            )
            self.started = True
            self.ever_started = True
            atexit.register(self.stop)
            self._atexit_registered = True
            _must_run(
                [
                    str(self.binaries["createdb"]),
                    "-h",
                    str(self.socket_directory),
                    "-p",
                    str(self.port),
                    "-U",
                    DATABASE_USER,
                    DATABASE_NAME,
                ],
                cwd=self.root,
                env=self.process_environment,
            )
            return self
        except BaseException:
            self.stop()
            raise

    def __exit__(self, *_error: object) -> None:
        self.stop()

    def stop(self) -> None:
        if self.started or (self.data_directory / "postmaster.pid").is_file():
            completed = _run(
                [
                    str(self.binaries["pg_ctl"]),
                    "-D",
                    str(self.data_directory),
                    "-m",
                    "fast",
                    "-w",
                    "stop",
                ],
                cwd=self.root,
                env=self.process_environment,
            )
            self.teardown.stop_exit_code = completed.returncode
            self.teardown.postgres_stopped = completed.returncode == 0
        else:
            self.teardown.stop_exit_code = 0
            self.teardown.postgres_stopped = True
        self.started = False
        if self._atexit_registered:
            atexit.unregister(self.stop)
            self._atexit_registered = False
        if self.data_directory.exists():
            shutil.rmtree(self.data_directory)
        self.teardown.data_directory_removed = not self.data_directory.exists()
        if self.socket_directory.exists():
            shutil.rmtree(self.socket_directory)
        self.teardown.socket_directory_removed = not self.socket_directory.exists()
        if self.home_directory.exists():
            shutil.rmtree(self.home_directory)
        self.teardown.temporary_home_removed = not self.home_directory.exists()

    def query_rows(self, statement: str) -> list[list[str]]:
        completed = _must_run(
            [
                str(self.binaries["psql"]),
                "-X",
                "-A",
                "-t",
                "-F",
                "\t",
                "-v",
                "ON_ERROR_STOP=1",
                "-h",
                str(self.socket_directory),
                "-p",
                str(self.port),
                "-U",
                DATABASE_USER,
                "-d",
                DATABASE_NAME,
                "-c",
                statement,
            ],
            cwd=self.root,
            env=self.process_environment,
        )
        return [line.split("\t") for line in completed.stdout.splitlines() if line]


def _source_paths(selectors: Sequence[str]) -> list[Path]:
    paths: set[Path] = {
        ENGINE_ROOT / "pyproject.toml",
        ENGINE_ROOT / "uv.lock",
        Path(__file__).resolve(),
    }
    for root in (
        ENGINE_ROOT / "src" / "elmos_build_cache",
        ENGINE_ROOT / "migrations",
        ENGINE_ROOT / "schemas",
    ):
        paths.update(
            path.resolve()
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
    for selector in selectors:
        paths.add((ENGINE_ROOT / selector.split("::", 1)[0]).resolve())
    return sorted(paths)


def _source_manifest(selectors: Sequence[str]) -> dict[str, Any]:
    files = []
    for path in _source_paths(selectors):
        content = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(ENGINE_ROOT).as_posix(),
                "sha256": _sha256_bytes(content),
                "size_bytes": len(content),
            }
        )
    return {"files": files, "manifest_sha256": _canonical_digest(files)}


def _pytest_counts(output: str) -> dict[str, int]:
    counts = {name: 0 for name in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")}
    summary = ""
    for line in reversed(output.splitlines()):
        if " in " in line and re.search(r"\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed)", line):
            summary = line
            break
    for amount, label in re.findall(r"(\d+) (passed|failed|errors?|skipped|xfailed|xpassed)", summary):
        key = "errors" if label in {"error", "errors"} else label
        counts[key] = int(amount)
    counts["collected"] = sum(counts.values())
    return counts


def _run_pytest(
    *,
    name: str,
    selectors: Sequence[str],
    cluster: DisposablePostgres,
    timeout: int,
) -> dict[str, Any]:
    argv = [
        sys.executable,
        "-m",
        "pytest",
        *selectors,
        "-o",
        "addopts=--strict-markers",
        "-ra",
    ]
    environment = dict(cluster.process_environment)
    environment["ELMOS_TEST_POSTGRES_DSN"] = cluster.dsn
    environment["PYTHONHASHSEED"] = "0"
    try:
        completed = _run(argv, cwd=ENGINE_ROOT, env=environment, timeout=timeout)
        raw_output = completed.stdout + completed.stderr
        exit_code = completed.returncode
        status = "PASSED" if completed.returncode == 0 else "FAILED"
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout
        stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
        raw_output = (stdout or "") + (stderr or "") + "\nPYTEST_TIMEOUT\n"
        exit_code = 124
        status = "TIMED_OUT"
    output = _redact(
        raw_output,
        cluster.dsn,
        str(cluster.socket_directory),
        str(cluster.root),
    )
    log_name = f"pytest-{name}.log"
    (cluster.root / log_name).write_text(output, encoding="utf-8")
    return {
        "name": name,
        "selectors": list(selectors),
        "argv": argv,
        "status": status,
        "exit_code": exit_code,
        "counts": _pytest_counts(output),
        "raw_log_role": f"pytest-{name}",
        "raw_log_path": log_name,
    }


def _pkg_version(name: str) -> str:
    for pkg in (name, f"{name}-binary", f"{name}_binary"):
        try:
            return importlib.metadata.version(pkg)
        except importlib.metadata.PackageNotFoundError:
            continue
    return "NOT_OBSERVED"


def _unobserved_environment(
    cluster: DisposablePostgres,
    binaries: dict[str, Path],
) -> dict[str, Any]:
    postgres_version = _must_run(
        [str(binaries["postgres"]), "--version"],
        cwd=cluster.root,
        env=cluster.process_environment,
    ).stdout.strip()
    psql_version = _must_run(
        [str(binaries["psql"]), "--version"],
        cwd=cluster.root,
        env=cluster.process_environment,
    ).stdout.strip()
    return {
        "os": platform.system().lower(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "uv": _command_version("uv", environment=cluster.process_environment, cwd=cluster.root),
        "pytest": _pkg_version("pytest"),
        "psycopg": _pkg_version("psycopg"),
        "postgres_server_binary": postgres_version,
        "postgres_client": psql_version,
        "postgres_runtime_observed": False,
        "server_version_num": "NOT_OBSERVED",
        "server_version": "NOT_OBSERVED",
        "server_encoding": "NOT_OBSERVED",
        "lc_collate": "NOT_OBSERVED",
        "lc_ctype": "NOT_OBSERVED",
        "timezone": "NOT_OBSERVED",
        "fsync": "NOT_OBSERVED",
        "synchronous_commit": "NOT_OBSERVED",
        "listen_addresses": "NOT_OBSERVED",
        "extensions": [],
        "socket_only": True,
        "data_class": "SYNTHETIC_TEST_FIXTURES",
        "production_database": False,
    }


def _fallback_environment() -> dict[str, Any]:
    return {
        "os": platform.system().lower(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "uv": "NOT_OBSERVED",
        "pytest": _pkg_version("pytest"),
        "psycopg": _pkg_version("psycopg"),
        "postgres_server_binary": "NOT_OBSERVED",
        "postgres_client": "NOT_OBSERVED",
        "postgres_runtime_observed": False,
        "server_version_num": "NOT_OBSERVED",
        "server_version": "NOT_OBSERVED",
        "server_encoding": "NOT_OBSERVED",
        "lc_collate": "NOT_OBSERVED",
        "lc_ctype": "NOT_OBSERVED",
        "timezone": "NOT_OBSERVED",
        "fsync": "NOT_OBSERVED",
        "synchronous_commit": "NOT_OBSERVED",
        "listen_addresses": "NOT_OBSERVED",
        "extensions": [],
        "socket_only": True,
        "data_class": "SYNTHETIC_TEST_FIXTURES",
        "production_database": False,
    }


def _environment_document(cluster: DisposablePostgres, binaries: dict[str, Path]) -> dict[str, Any]:
    document = _unobserved_environment(cluster, binaries)
    settings = cluster.query_rows(
        "SELECT current_setting('server_version_num'), current_setting('server_version'), "
        "current_setting('server_encoding'), db.datcollate, db.datctype, "
        "current_setting('TimeZone'), current_setting('fsync'), "
        "current_setting('synchronous_commit'), current_setting('listen_addresses') "
        "FROM pg_database AS db WHERE db.datname = current_database()"
    )
    if len(settings) != 1 or len(settings[0]) != 9:
        raise RuntimeError("POSTGRES_ENVIRONMENT_QUERY_INVALID")
    row = settings[0]
    extensions = [
        item[0] for item in cluster.query_rows("SELECT extname || '=' || extversion FROM pg_extension ORDER BY extname")
    ]
    document.update(
        {
            "postgres_runtime_observed": True,
            "server_version_num": row[0],
            "server_version": row[1],
            "server_encoding": row[2],
            "lc_collate": row[3],
            "lc_ctype": row[4],
            "timezone": row[5],
            "fsync": row[6],
            "synchronous_commit": row[7],
            "listen_addresses": row[8],
            "extensions": extensions,
            "socket_only": row[8] == "",
        }
    )
    return document


def _database_documents(cluster: DisposablePostgres) -> tuple[dict[str, Any], dict[str, Any]]:
    ledger_names = [row[0] for row in cluster.query_rows("SELECT name FROM schema_migrations ORDER BY name")]
    ledger = {
        "migration_names": ledger_names,
        "migration_ledger_sha256": _canonical_digest(ledger_names),
    }
    introspection: dict[str, Any] = {
        "table": cluster.query_rows(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='cache_slo_control_events_v12'"
        ),
        "constraints": cluster.query_rows(
            "SELECT conname, contype, pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conrelid='cache_slo_control_events_v12'::regclass ORDER BY conname"
        ),
        "indexes": cluster.query_rows(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND tablename='cache_slo_control_events_v12' ORDER BY indexname"
        ),
        "triggers": cluster.query_rows(
            "SELECT tgname, pg_get_triggerdef(oid) FROM pg_trigger "
            "WHERE tgrelid='cache_slo_control_events_v12'::regclass AND NOT tgisinternal "
            "ORDER BY tgname"
        ),
    }
    introspection["introspection_sha256"] = _canonical_digest(introspection)
    return ledger, introspection


def _unobserved_database_documents() -> tuple[dict[str, Any], dict[str, Any]]:
    ledger = {
        "state": "NOT_RUN",
        "migration_names": [],
        "migration_ledger_sha256": _canonical_digest([]),
    }
    introspection: dict[str, Any] = {
        "state": "NOT_RUN",
        "table": [],
        "constraints": [],
        "indexes": [],
        "triggers": [],
    }
    introspection["introspection_sha256"] = _canonical_digest(introspection)
    return ledger, introspection


def _evidence_item(root: Path, role: str, path: str, media_type: str) -> dict[str, Any]:
    content = (root / path).read_bytes()
    return {
        "role": role,
        "path": path,
        "media_type": media_type,
        "size_bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def _receipt_digest(receipt: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    return _canonical_digest(unsigned)


def _validate_receipt(receipt: dict[str, Any]) -> None:
    import jsonschema  # type: ignore[import-untyped]

    schema_path = (
        ENGINE_ROOT
        / "src"
        / "elmos_build_cache"
        / "_data"
        / "schemas"
        / "local-postgres-qualification-receipt.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(receipt),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"{'/'.join(str(part) for part in error.absolute_path) or '$'}:{error.message}" for error in errors[:10]
        )
        raise RuntimeError(f"QUALIFICATION_RECEIPT_SCHEMA_INVALID:{detail}")
    if receipt.get("receipt_sha256") != _receipt_digest(receipt):
        raise RuntimeError("QUALIFICATION_RECEIPT_DIGEST_INVALID")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-source-revision")
    parser.add_argument("--executor-id", required=True)
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--confirm-disposable", required=True, choices=[CONFIRMATION])
    parser.add_argument("--postgres-bin", type=Path, default=DEFAULT_POSTGRES_BIN)
    parser.add_argument("--output-parent", type=Path, default=TMP_ALIAS)
    parser.add_argument("--metadata-selector", action="append", default=[])
    parser.add_argument("--slo-selector", action="append", default=[])
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--print-plan", action="store_true")
    return parser


def _plan(arguments: argparse.Namespace) -> dict[str, Any]:
    metadata_selectors = arguments.metadata_selector or [METADATA_TEST_FILE]
    metadata = [_validate_selector(item, METADATA_TEST_FILE) for item in metadata_selectors]
    slo = [_validate_selector(item, SLO_TEST_FILE) for item in arguments.slo_selector]
    if arguments.timeout_seconds < 1 or arguments.timeout_seconds > 7_200:
        raise ValueError("timeout-seconds must be between 1 and 7200")
    if arguments.expected_source_revision is not None and not re.fullmatch(
        r"[0-9a-f]{40}", arguments.expected_source_revision
    ):
        raise ValueError("expected-source-revision must be a full lowercase Git SHA")
    executor_id = _validate_public_identifier("executor-id", arguments.executor_id)
    authorization_ref = _validate_public_identifier("authorization-ref", arguments.authorization_ref)
    _validated_tmp_parent(arguments.output_parent)
    return {
        "schema_version": "1.0.0",
        "kind": "elmos.build-cache.local-postgres-qualification-plan/v1",
        "source_revision": "READ_FROM_GIT_AT_EXECUTION",
        "expected_source_revision": arguments.expected_source_revision,
        "executor_id": executor_id,
        "authorization_ref": authorization_ref,
        "metadata_selectors": metadata,
        "slo_selectors": slo,
        "slo_service_live_postgres": "PLANNED" if slo else "NOT_RUN",
        "temp_root": f"{TMP_ALIAS}/mkdtemp",
        "socket_only": True,
        "external_dsn_accepted": False,
        "dsn_recorded": False,
        "secrets_recorded": False,
        "fsync": "on",
        "synchronous_commit": "on",
        "production_database": False,
    }


def execute(arguments: argparse.Namespace) -> tuple[int, Path]:
    plan = _plan(arguments)
    binaries = _required_binaries(arguments.postgres_bin)
    output_parent = _validated_tmp_parent(arguments.output_parent, create=True)
    selectors = [*plan["metadata_selectors"], *plan["slo_selectors"]]
    started_at = _utc_now()
    cluster = DisposablePostgres(binaries, output_parent)
    source_before = _source_manifest(selectors)
    source_after = source_before
    source_state: dict[str, Any] = {"revision": "NOT_OBSERVED", "dirty": True}
    environment = _fallback_environment()
    ledger, introspection = _unobserved_database_documents()
    test_runs: list[dict[str, Any]] = []
    failure_status: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    try:
        source_state = _git_source_state(environment=cluster.process_environment)
        if (
            arguments.expected_source_revision is not None
            and source_state["revision"] != arguments.expected_source_revision
        ):
            raise ValueError("EXPECTED_SOURCE_REVISION_MISMATCH")
        environment = _unobserved_environment(cluster, binaries)
        with cluster:
            environment = _environment_document(cluster, binaries)
            test_runs.append(
                _run_pytest(
                    name="metadata-store",
                    selectors=plan["metadata_selectors"],
                    cluster=cluster,
                    timeout=arguments.timeout_seconds,
                )
            )
            if plan["slo_selectors"]:
                test_runs.append(
                    _run_pytest(
                        name="slo-service-live-postgres",
                        selectors=plan["slo_selectors"],
                        cluster=cluster,
                        timeout=arguments.timeout_seconds,
                    )
                )
            ledger, introspection = _database_documents(cluster)
    except subprocess.TimeoutExpired as error:
        failure_status = "BLOCKED_TIMEOUT"
        failure_code = "COMMAND_TIMEOUT"
        failure_message = str(error)
    except ValueError as error:
        failure_status = (
            "BLOCKED_SOURCE_REVISION_MISMATCH" if str(error) == "EXPECTED_SOURCE_REVISION_MISMATCH" else "BLOCKED_INPUT"
        )
        failure_code = str(error)
        failure_message = str(error)
    except (OSError, RuntimeError) as error:
        failure_status = "BLOCKED_RUNTIME" if cluster.ever_started else "BLOCKED_PROVISIONING"
        failure_code = type(error).__name__.upper()
        failure_message = str(error)
    finally:
        cluster.stop()
        try:
            source_after = _source_manifest(selectors)
        except OSError as error:
            failure_status = failure_status or "BLOCKED_SOURCE_DRIFT"
            failure_code = failure_code or "SOURCE_MANIFEST_UNREADABLE"
            failure_message = failure_message or str(error)

    source_stable = source_before["manifest_sha256"] == source_after["manifest_sha256"]
    if not cluster.server_log.is_file():
        cluster.server_log.write_text("POSTGRES_SERVER_LOG_NOT_AVAILABLE\n", encoding="utf-8")
    cluster.server_log.write_text(
        _redact(
            cluster.server_log.read_text(encoding="utf-8", errors="replace"),
            cluster.dsn,
            str(cluster.socket_directory),
            str(cluster.root),
        ),
        encoding="utf-8",
    )
    if failure_status is not None:
        _write_json(
            cluster.root / "qualification-error.json",
            {
                "status": failure_status,
                "error_code": failure_code,
                "message": _redact(
                    failure_message or "NOT_AVAILABLE",
                    cluster.dsn,
                    str(cluster.socket_directory),
                    str(cluster.root),
                ),
            },
        )

    _write_json(cluster.root / "environment.json", environment)
    _write_json(cluster.root / "migration-ledger.json", ledger)
    _write_json(cluster.root / "schema-introspection.json", introspection)
    _write_json(
        cluster.root / "source-manifest.json",
        {"before": source_before, "after": source_after, "stable": source_stable},
    )
    _write_json(cluster.root / "teardown.json", cluster.teardown.to_dict())

    tests_timed_out = any(item["status"] == "TIMED_OUT" for item in test_runs)
    tests_passed = bool(test_runs) and all(item["status"] == "PASSED" for item in test_runs)
    if failure_status is not None:
        status = failure_status
    elif not source_stable:
        status = "BLOCKED_SOURCE_DRIFT"
    elif cluster.teardown.status != "COMPLETE":
        status = "BLOCKED_INCOMPLETE_TEARDOWN"
    elif tests_timed_out:
        status = "BLOCKED_TIMEOUT"
    elif not tests_passed:
        status = "FAILED"
    elif plan["slo_selectors"]:
        status = "PASSED_LOCAL_METADATA_AND_SLO"
    else:
        status = "PASSED_LOCAL_METADATA_ONLY"

    evidence = [
        _evidence_item(cluster.root, "environment", "environment.json", "application/json"),
        _evidence_item(cluster.root, "migration-ledger", "migration-ledger.json", "application/json"),
        _evidence_item(
            cluster.root,
            "schema-introspection",
            "schema-introspection.json",
            "application/json",
        ),
        _evidence_item(cluster.root, "source-manifest", "source-manifest.json", "application/json"),
        _evidence_item(cluster.root, "postgres-server-log", "postgres-server.log", "text/plain"),
        _evidence_item(cluster.root, "teardown", "teardown.json", "application/json"),
    ]
    if failure_status is not None:
        evidence.append(
            _evidence_item(
                cluster.root,
                "qualification-error",
                "qualification-error.json",
                "application/json",
            )
        )
    for test_run in test_runs:
        evidence.append(
            _evidence_item(
                cluster.root,
                test_run["raw_log_role"],
                test_run["raw_log_path"],
                "text/plain",
            )
        )

    metadata_run = next((item for item in test_runs if item["name"] == "metadata-store"), None)
    slo_run = next(
        (item for item in test_runs if item["name"] == "slo-service-live-postgres"),
        None,
    )
    limitations = ["SELF_ATTESTED_LOCAL_ENGINEERING_EVIDENCE"]
    if not plan["slo_selectors"]:
        limitations.append("SLO_SERVICE_LIVE_POSTGRES_NOT_RUN")
    if failure_code is not None:
        limitations.append("QUALIFICATION_BLOCKED")
    exit_code = 0 if status.startswith("PASSED_LOCAL_") else (1 if status == "FAILED" else 2)

    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "kind": RECEIPT_KIND,
        "receipt_id": cluster.root.name,
        "evidence_class": "LOCAL_EXECUTED_SELF_ATTESTED",
        "status": status,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "source": {
            "revision_source": "git-rev-parse-head",
            "revision": source_state["revision"],
            "expected_revision": arguments.expected_source_revision,
            "dirty": source_state["dirty"],
            "manifest_sha256_before": source_before["manifest_sha256"],
            "manifest_sha256_after": source_after["manifest_sha256"],
            "stable": source_stable,
        },
        "environment": environment,
        "safety": {
            "authorization_ref": arguments.authorization_ref,
            "disposable_confirmation": True,
            "temp_root_kind": "mkdtemp-under-/tmp",
            "socket_only": True,
            "external_dsn_accepted": False,
            "dsn_recorded": False,
            "secrets_recorded": False,
            "production_database": False,
            "production_writes": False,
            "durability_weakened": False,
        },
        "test_runs": test_runs,
        "tests": {
            "metadata_store_live_postgres": (metadata_run["status"] if metadata_run is not None else "NOT_RUN"),
            "slo_service_live_postgres": slo_run["status"] if slo_run is not None else "NOT_RUN",
        },
        "database": {
            "migration_ledger_sha256": ledger["migration_ledger_sha256"],
            "schema_introspection_sha256": introspection["introspection_sha256"],
        },
        "raw_evidence": evidence,
        "executor": {"identity": arguments.executor_id, "role": "executor"},
        "independent_verifier": {"state": "NOT_RUN"},
        "external_states": {
            "ci": "NOT_RUN",
            "production": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        },
        "limitations": limitations,
        "failure": {
            "state": "NOT_APPLICABLE" if failure_code is None else "BLOCKED",
            "error_code": failure_code,
        },
        "teardown": cluster.teardown.to_dict(),
        "exit_code": exit_code,
    }
    receipt["receipt_sha256"] = _receipt_digest(receipt)
    _validate_receipt(receipt)
    _write_json(cluster.root / "receipt.json", receipt)
    return exit_code, cluster.root


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _build_parser().parse_args(argv)
    try:
        plan = _plan(arguments)
        if arguments.print_plan:
            print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        previous_term = signal.getsignal(signal.SIGTERM)

        def terminate(signum: int, _frame: object) -> None:
            raise SystemExit(128 + signum)

        signal.signal(signal.SIGTERM, terminate)
        try:
            exit_code, output = execute(arguments)
        finally:
            signal.signal(signal.SIGTERM, previous_term)
        print(json.dumps({"exit_code": exit_code, "evidence_directory": str(output)}))
        return exit_code
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        print(_redact(f"LOCAL_POSTGRES_QUALIFICATION_BLOCKED:{error}"), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
