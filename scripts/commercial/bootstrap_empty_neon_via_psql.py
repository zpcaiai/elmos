#!/usr/bin/env python3
"""Bootstrap an empty Neon database when a managed host blocks JDBC TLS.

This path is intentionally narrower than ordinary Flyway upgrades: the target
must be an explicitly confirmed empty Neon database, every migration and its
history record share one transaction, and the final history is reconciled
against the repository. Normal upgrades remain owned by ``migrate_neon.sh``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION_DIRECTORY = (
    ROOT / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration"
)
MIGRATION_PATTERN = re.compile(r"^V(?P<version>[1-9][0-9]*)__([A-Za-z0-9_]+)\.sql$")


class BootstrapBlocked(RuntimeError):
    """The empty-database bootstrap contract was not satisfied."""


@dataclass(frozen=True)
class Migration:
    version: int
    description: str
    path: Path
    checksum: int


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise BootstrapBlocked(f"{name}_REQUIRED")
    return value


def flyway_checksum(path: Path) -> int:
    checksum = 0
    with path.open(encoding="utf-8-sig") as source:
        for line in source:
            checksum = zlib.crc32(line.rstrip("\r\n").encode("utf-8"), checksum)
    return checksum - 2**32 if checksum >= 2**31 else checksum


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def discover_migrations(directory: Path = MIGRATION_DIRECTORY) -> tuple[Migration, ...]:
    migrations: list[Migration] = []
    for path in directory.glob("V*__*.sql"):
        match = MIGRATION_PATTERN.fullmatch(path.name)
        if match is None:
            raise BootstrapBlocked(f"MIGRATION_NAME_INVALID:{path.name}")
        migrations.append(
            Migration(
                version=int(match.group("version")),
                description=match.group(2).replace("_", " "),
                path=path,
                checksum=flyway_checksum(path),
            )
        )
    migrations.sort(key=lambda migration: migration.version)
    observed = [migration.version for migration in migrations]
    if not observed:
        raise BootstrapBlocked("MIGRATION_INVENTORY_EMPTY")
    expected = list(range(1, observed[-1] + 1))
    missing = sorted(set(expected) - set(observed))
    duplicates = sorted(version for version in set(observed) if observed.count(version) > 1)
    if observed != expected:
        raise BootstrapBlocked(
            "MIGRATION_VERSION_SEQUENCE_INVALID:"
            f"expected={expected}:observed={observed}:missing={missing}:"
            f"duplicates={duplicates}"
        )
    return tuple(migrations)


def connection_arguments() -> tuple[list[str], dict[str, str]]:
    host = required_environment("ELMOS_COMMERCIAL_DATABASE_EXPECTED_HOST")
    database = required_environment("ELMOS_COMMERCIAL_DATABASE_EXPECTED_DATABASE")
    user = required_environment("ELMOS_COMMERCIAL_DATABASE_MIGRATION_USERNAME")
    required_environment("PGPASSWORD")
    if not host.endswith(".neon.tech"):
        raise BootstrapBlocked("TARGET_HOST_IS_NOT_NEON")
    if os.environ.get("ELMOS_COMMERCIAL_DATABASE_EMPTY_BOOTSTRAP_CONFIRMED") != "true":
        raise BootstrapBlocked("EMPTY_BOOTSTRAP_CONFIRMATION_REQUIRED")
    environment = dict(os.environ)
    environment["PGSSLMODE"] = "require"
    return (
        [
            required_environment("PSQL_PATH"),
            "--host",
            host,
            "--port",
            os.environ.get("ELMOS_COMMERCIAL_DATABASE_PORT", "5432"),
            "--username",
            user,
            "--dbname",
            database,
            "--no-psqlrc",
            "--set",
            "ON_ERROR_STOP=1",
        ],
        environment,
    )


def run_psql(
    base_arguments: list[str],
    environment: dict[str, str],
    *arguments: str,
    capture: bool = False,
) -> str:
    completed = subprocess.run(
        [*base_arguments, *arguments],
        cwd=ROOT,
        env=environment,
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "psql failed")[-2_000:]
        raise BootstrapBlocked(f"PSQL_FAILED:{detail}")
    return completed.stdout if capture else ""


def require_empty_target(base_arguments: list[str], environment: dict[str, str]) -> None:
    result = run_psql(
        base_arguments,
        environment,
        "--tuples-only",
        "--no-align",
        "--field-separator",
        "|",
        "--command",
        (
            "SELECT "
            "(SELECT count(*) FROM information_schema.tables "
            " WHERE table_schema NOT IN "
            " ('pg_catalog','information_schema','neon_auth') "
            " AND table_type='BASE TABLE'),"
            "to_regclass('public.flyway_schema_history') IS NOT NULL"
        ),
        capture=True,
    ).strip()
    if result != "0|f":
        raise BootstrapBlocked(f"TARGET_DATABASE_NOT_EMPTY:{result}")


def create_history(base_arguments: list[str], environment: dict[str, str]) -> None:
    run_psql(
        base_arguments,
        environment,
        "--single-transaction",
        "--command",
        """
        CREATE TABLE public.flyway_schema_history (
          installed_rank integer NOT NULL,
          version varchar(50),
          description varchar(200) NOT NULL,
          type varchar(20) NOT NULL,
          script varchar(1000) NOT NULL,
          checksum integer,
          installed_by varchar(100) NOT NULL,
          installed_on timestamp without time zone NOT NULL DEFAULT now(),
          execution_time integer NOT NULL,
          success boolean NOT NULL,
          CONSTRAINT flyway_schema_history_pk PRIMARY KEY (installed_rank)
        );
        CREATE INDEX flyway_schema_history_s_idx
          ON public.flyway_schema_history (success);
        INSERT INTO public.flyway_schema_history (
          installed_rank, version, description, type, script, checksum,
          installed_by, execution_time, success
        ) VALUES (
          1, '0', '<< Flyway Baseline >>', 'BASELINE',
          'Neon public schema bootstrap', NULL, current_user, 0, true
        );
        """,
    )


def apply_migration(
    base_arguments: list[str],
    environment: dict[str, str],
    migration: Migration,
) -> None:
    started = time.monotonic()
    execution_time = max(0, round((time.monotonic() - started) * 1_000))
    history_insert = f"""
        INSERT INTO public.flyway_schema_history (
          installed_rank, version, description, type, script, checksum,
          installed_by, execution_time, success
        ) VALUES (
          {migration.version + 1}, {sql_literal(str(migration.version))},
          {sql_literal(migration.description)}, 'SQL',
          {sql_literal(migration.path.name)}, {migration.checksum}, current_user,
          {execution_time}, true
        )
    """
    run_psql(
        base_arguments,
        environment,
        "--single-transaction",
        "--file",
        str(migration.path),
        "--command",
        history_insert,
    )


def verify_history(
    base_arguments: list[str],
    environment: dict[str, str],
    migrations: tuple[Migration, ...],
) -> None:
    output = run_psql(
        base_arguments,
        environment,
        "--tuples-only",
        "--no-align",
        "--field-separator",
        "|",
        "--command",
        (
            "SELECT version, script, checksum, success "
            "FROM public.flyway_schema_history "
            "WHERE type='SQL' ORDER BY installed_rank"
        ),
        capture=True,
    )
    observed = [
        (int(version), script, int(checksum), success == "t")
        for version, script, checksum, success in (
            line.split("|") for line in output.splitlines() if line.strip()
        )
    ]
    expected = [
        (migration.version, migration.path.name, migration.checksum, True)
        for migration in migrations
    ]
    if observed != expected:
        raise BootstrapBlocked("FLYWAY_HISTORY_RECONCILIATION_FAILED")


def main() -> int:
    try:
        migrations = discover_migrations()
        base_arguments, environment = connection_arguments()
        require_empty_target(base_arguments, environment)
        create_history(base_arguments, environment)
        for migration in migrations:
            apply_migration(base_arguments, environment, migration)
        verify_history(base_arguments, environment, migrations)
    except BootstrapBlocked as error:
        print(f"Neon empty bootstrap blocked: {error}", file=sys.stderr)
        return 1
    print(
        f"Neon empty bootstrap completed: {len(migrations)} migrations reconciled.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
