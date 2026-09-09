"""Connect generated and platform runtimes to an operator-supplied PostgreSQL.

The URL never enters argv or logs. It is read from an owner-only file. Loopback
hosts are rejected unless the operator explicitly opts in for a closed drill.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

class HostedPostgresError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}
_VERSION_RE = re.compile(r"PostgreSQL (\d+\.\d+)")


@dataclass(frozen=True)
class HostedPostgresBinding:
    host: str
    port: int
    database: str
    version: str
    sslmode: str
    source: str
    loopback_opt_in: bool

    def as_mapping(self) -> dict[str, str | int | bool]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "version": self.version,
            "sslmode": self.sslmode,
            "source": self.source,
            "loopback_opt_in": self.loopback_opt_in,
            "production_delivery_status": "NOT_RUN",
            "external_certification_status": "NOT_RUN",
        }


def read_url_file(path: Path) -> str:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise HostedPostgresError("HOSTED_POSTGRES_URL_FILE_UNSAFE")
    info = path.stat()
    if info.st_size < 16 or info.st_size > 4_096 or info.st_mode & 0o077:
        raise HostedPostgresError("HOSTED_POSTGRES_URL_FILE_UNSAFE")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise HostedPostgresError("HOSTED_POSTGRES_URL_FILE_UNSAFE")
    url = path.read_text(encoding="utf-8").strip()
    if "\n" in url or url.lower().startswith("postgres://"):
        raise HostedPostgresError("HOSTED_POSTGRES_URL_INVALID")
    if not url.startswith("postgresql://"):
        raise HostedPostgresError("HOSTED_POSTGRES_URL_SCHEME_UNSUPPORTED")
    return url


def bind_hosted_postgres(
    url_file: Path,
    *,
    allow_loopback: bool = False,
    psql: str = "psql",
) -> HostedPostgresBinding:
    url = read_url_file(url_file)
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host or parsed.username is None or not parsed.path or parsed.path == "/":
        raise HostedPostgresError("HOSTED_POSTGRES_URL_INVALID")
    loopback = host in _LOOPBACK
    if loopback and not allow_loopback:
        raise HostedPostgresError("HOSTED_POSTGRES_LOOPBACK_FORBIDDEN")
    sslmode = "disable" if loopback else "require"
    if "sslmode=" in (parsed.query or ""):
        for item in parsed.query.split("&"):
            if item.startswith("sslmode="):
                sslmode = item.split("=", 1)[1]
    if not loopback and sslmode in {"disable", "allow"}:
        raise HostedPostgresError("HOSTED_POSTGRES_TLS_REQUIRED")
    probe = subprocess.run(  # noqa: S603
        [psql, url, "-v", "ON_ERROR_STOP=1", "-tA", "-c", "SHOW server_version;"],
        check=False,
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        raise HostedPostgresError("HOSTED_POSTGRES_UNREACHABLE")
    version = probe.stdout.strip().splitlines()[0].strip()
    if not version:
        raise HostedPostgresError("HOSTED_POSTGRES_VERSION_UNREADABLE")
    return HostedPostgresBinding(
        host=host,
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
        version=version,
        sslmode=sslmode,
        source=str(url_file),
        loopback_opt_in=loopback and allow_loopback,
    )


def apply_migration(url_file: Path, migration: Path, *, psql: str = "psql") -> None:
    url = read_url_file(url_file)
    if not migration.is_file() or migration.is_symlink():
        raise HostedPostgresError("HOSTED_POSTGRES_MIGRATION_UNSAFE")
    applied = subprocess.run(  # noqa: S603
        [psql, url, "-v", "ON_ERROR_STOP=1", "-f", str(migration)],
        check=False,
        capture_output=True,
        text=True,
    )
    if applied.returncode != 0:
        raise HostedPostgresError("HOSTED_POSTGRES_MIGRATION_FAILED")


def assert_no_database_credentials_on_runner(environment: dict[str, str]) -> None:
    forbidden = (
        "DATABASE_URL",
        "ELMOS_DATABASE_URL",
        "ELMOS_HOSTED_POSTGRES_URL",
        "POSTGRES_PASSWORD",
        "PGPASSWORD",
    )
    present = [name for name in forbidden if environment.get(name)]
    if present:
        raise HostedPostgresError("RUNNER_HOST_HOLDS_DATABASE_CREDENTIALS:" + ",".join(present))
    if environment.get("ELMOS_HOSTED_POSTGRES_URL_FILE") and environment.get(
        "ELMOS_RUNNER_ROLE"
    ) == "runner-agent":
        raise HostedPostgresError("RUNNER_HOST_HOLDS_DATABASE_CREDENTIALS:ELMOS_HOSTED_POSTGRES_URL_FILE")
