"""Restore drill for generation-hosted PostgreSQL.

A successful local dump/restore is LOCAL_DRILL evidence. It never becomes
offsite DR, RPO/RTO, or certification evidence.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from .hosted_postgres import HostedPostgresError, read_url_file


class RestoreDrillError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def run_restore_drill(
    *,
    source_url_file: Path,
    restore_url_file: Path,
    work_dir: Path,
    pg_dump: str = "pg_dump",
    psql: str = "psql",
) -> dict[str, Any]:
    source = read_url_file(source_url_file)
    restore = read_url_file(restore_url_file)
    if source == restore:
        raise RestoreDrillError("RESTORE_DRILL_SOURCE_EQUALS_TARGET")
    work_dir.mkdir(parents=True, exist_ok=True)
    dump = work_dir / "generation-hosted.dump.sql"
    dumped = _run([pg_dump, "--no-owner", "--no-privileges", source])
    if dumped.returncode != 0:
        raise RestoreDrillError("RESTORE_DRILL_DUMP_FAILED")
    dump.write_text(dumped.stdout, encoding="utf-8")
    dump.chmod(0o600)
    digest = hashlib.sha256(dump.read_bytes()).hexdigest()
    restored = _run([psql, restore, "-v", "ON_ERROR_STOP=1", "-f", str(dump)])
    if restored.returncode != 0:
        raise RestoreDrillError("RESTORE_DRILL_RESTORE_FAILED")
    source_count = _run(
        [psql, source, "-tA", "-c", "SELECT COUNT(*) FROM information_schema.tables;"]
    )
    restore_count = _run(
        [psql, restore, "-tA", "-c", "SELECT COUNT(*) FROM information_schema.tables;"]
    )
    if source_count.returncode != 0 or restore_count.returncode != 0:
        raise RestoreDrillError("RESTORE_DRILL_VERIFY_FAILED")
    if source_count.stdout.strip() != restore_count.stdout.strip():
        raise RestoreDrillError("RESTORE_DRILL_TABLE_COUNT_MISMATCH")
    receipt = {
        "schema_version": "1.0.0",
        "kind": "elmos.generation-hosted-restore-drill",
        "status": "PASSED_LOCAL_DRILL",
        "dump_sha256": digest,
        "table_count": source_count.stdout.strip(),
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "production_delivery_status": "NOT_RUN",
        "offsite_retention_status": "NOT_RUN",
        "rpo_rto_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "external_certification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "statement": (
            "Local dump/restore succeeded against the supplied PostgreSQL pair. "
            "This is not offsite backup, PITR, cross-region DR, or certification."
        ),
    }
    (work_dir / "restore-drill-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


# Re-export so callers can catch URL-file failures uniformly.
_ = HostedPostgresError
