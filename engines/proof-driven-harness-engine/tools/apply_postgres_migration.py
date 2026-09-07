#!/usr/bin/env python3
"""Apply V001 transactionally and record its detached source digest.

The owner DSN is read from an environment variable so it is not exposed in the
process argument list.  The migration is opened once with ``O_NOFOLLOW`` when
available, bounded, hashed from those exact bytes, executed in one PostgreSQL
transaction, and recorded in ``migration_digest_ledger`` before commit.

Success writes one JSON object to stdout with status ``APPLIED`` or
``ALREADY_APPLIED``.  Failures write a redacted JSON object to stderr and exit
2.  The tool never accepts a production application, certifier, or scheduler
role in place of the exact deployment owner role.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


MAX_MIGRATION_BYTES = 8 * 1024 * 1024
MIGRATION_NAME = "V001__proof_harness_core.sql"
SCHEMA_VERSION = 1
FORBIDDEN_ROLE_MARKERS = ("app", "runtime", "certifier", "scheduler")


def _digest_bytes(content: bytes) -> str:
    import hashlib

    prefix = b"elmos.proof-harness.v1\x00postgres-migration-file\x00"
    return "sha256:" + hashlib.sha256(prefix + content).hexdigest()


def _read_once(path: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("migration source is not a regular file")
        if metadata.st_size < 1 or metadata.st_size > MAX_MIGRATION_BYTES:
            raise RuntimeError("migration source size is outside the allowed bound")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise RuntimeError("migration source changed during its single-FD read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise RuntimeError("migration source grew during its single-FD read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def apply(
    *,
    dsn: str,
    expected_owner_role: str,
    migration_path: Path,
) -> dict[str, Any]:
    if not dsn.strip():
        raise RuntimeError("owner DSN is not configured")
    if not expected_owner_role.strip():
        raise RuntimeError("expected owner role is required")
    if any(marker in expected_owner_role.casefold() for marker in FORBIDDEN_ROLE_MARKERS):
        raise RuntimeError("expected owner role name is reserved for a non-owner service role")
    if migration_path.name != MIGRATION_NAME:
        raise RuntimeError(f"only {MIGRATION_NAME} may be applied by this tool")
    source = _read_once(migration_path)
    source_digest = _digest_bytes(source)
    sql = source.decode("utf-8", errors="strict")
    try:
        psycopg = importlib.import_module("psycopg")
    except ImportError as exc:
        raise RuntimeError("psycopg[binary]==3.2.13 is not installed") from exc
    version = str(getattr(psycopg, "__version__", ""))
    if not version.startswith("3.2."):
        raise RuntimeError("migration applicator requires the pinned psycopg 3.2 line")

    with psycopg.connect(dsn, autocommit=False) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_user,r.rolsuper,r.rolbypassrls,"
                "has_database_privilege(current_user,current_database(),'CREATE') "
                "FROM pg_roles r WHERE r.rolname=current_user"
            )
            role_name, superuser, bypass_rls, can_create = cursor.fetchone()
            if role_name != expected_owner_role:
                raise RuntimeError("connected role does not match the exact configured migration owner")
            if superuser or bypass_rls or not can_create:
                raise RuntimeError("migration owner must be NOSUPERUSER, NOBYPASSRLS, and hold database CREATE")
            cursor.execute("SELECT to_regclass('proof_harness_runtime.migration_digest_ledger')")
            ledger_exists = cursor.fetchone()[0] is not None
            if ledger_exists:
                cursor.execute(
                    "SELECT content_sha256 FROM proof_harness_runtime.migration_digest_ledger "
                    "WHERE version=%s AND migration_name=%s",
                    (SCHEMA_VERSION, MIGRATION_NAME),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("migration schema exists without its required digest ledger entry")
                if row[0] != source_digest:
                    raise RuntimeError("installed migration digest conflicts with the exact source bytes")
                connection.rollback()
                return {
                    "status": "ALREADY_APPLIED",
                    "version": SCHEMA_VERSION,
                    "migration": MIGRATION_NAME,
                    "contentSha256": source_digest,
                    "ownerRole": role_name,
                }
            cursor.execute("SELECT to_regnamespace('proof_harness_runtime')")
            if cursor.fetchone()[0] is not None:
                raise RuntimeError("partial proof_harness_runtime schema exists without a digest ledger")
            cursor.execute(sql)
            cursor.execute(
                "INSERT INTO proof_harness_runtime.migration_digest_ledger("
                "version,migration_name,content_sha256,recorded_by) VALUES (%s,%s,%s,current_user)",
                (SCHEMA_VERSION, MIGRATION_NAME, source_digest),
            )
        connection.commit()
    return {
        "status": "APPLIED",
        "version": SCHEMA_VERSION,
        "migration": MIGRATION_NAME,
        "contentSha256": source_digest,
        "ownerRole": expected_owner_role,
    }


def main(argv: list[str] | None = None) -> int:
    default_migration = Path(__file__).resolve().parents[1] / "migrations" / MIGRATION_NAME
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn-env", default="ELMOS_MIGRATION_OWNER_DSN")
    parser.add_argument("--expected-owner-role", required=True)
    parser.add_argument("--migration", type=Path, default=default_migration)
    arguments = parser.parse_args(argv)
    try:
        result = apply(
            dsn=os.environ.get(arguments.dsn_env, ""),
            expected_owner_role=arguments.expected_owner_role,
            migration_path=arguments.migration,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "FAILED",
                    "code": "MIGRATION_REJECTED",
                    "reason": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
