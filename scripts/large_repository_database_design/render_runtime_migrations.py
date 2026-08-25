#!/usr/bin/env python3
"""Render the pinned PostgreSQL 16/17 migration compatibility overlay.

The supplied package is immutable. Its V020 migration partitions two event
tables by run/session identifiers while also declaring tenant-scoped unique
event identifiers. PostgreSQL requires every unique key on a partitioned table
to include the partition key, so that source cannot be executed as written.

This renderer verifies the source checksum manifest and applies two exact,
digest-bound substitutions to a temporary runtime copy. The compatibility
copy partitions by tenant_id, preserving every declared primary/unique key.
It is bounded engineering tooling, not a production migration rewrite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


EXPECTED_CHECKSUMS_SHA256 = (
    "6bf7c561ccc3e31ed296717d20bc9f3915d149896a1d2b1dd9a3c7094a9fc07a"
)
PATCHED_MIGRATION = "V020__runs_tasks_sessions_and_recovery.sql"
EXPECTED_PATCH_SOURCE_SHA256 = (
    "1d9b6641ed8f2f423938ff067de56a33b86dc754220832d423a078b81ac5bc6e"
)
EXPECTED_PATCH_OUTPUT_SHA256 = (
    "4cc21c57b6fe81039b752669fb1d9246f68f4e06568f07104db8f92c1f0dd139"
)
EXPECTED_MIGRATIONS = (
    "V001__extensions_schemas_and_helpers.sql",
    "V010__tenancy_projects_jobs_and_admission.sql",
    PATCHED_MIGRATION,
    "V030__artifacts_manifests_staging_and_checkpoints.sql",
    "V040__repository_intelligence_semantic_ir_and_capabilities.sql",
    "V045__project_generation_and_transformation.sql",
    "V050__verification_evidence_gates_and_repair.sql",
    "V060__model_tool_metering_cost_eta_and_cache.sql",
    "V070__integration_learning_deployment_and_audit.sql",
    "V080__cross_links_rls_and_read_models.sql",
    "V090__transactional_runtime_functions.sql",
)
PATCHES = (
    (b") PARTITION BY HASH (run_id);", b") PARTITION BY HASH (tenant_id);"),
    (b") PARTITION BY HASH (session_id);", b") PARTITION BY HASH (tenant_id);"),
)


class RuntimeMigrationError(RuntimeError):
    """Raised when source identity or compatibility output is not exact."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def parse_checksums(package_root: Path) -> dict[str, str]:
    checksum_path = package_root / "CHECKSUMS.sha256"
    if not checksum_path.is_file() or checksum_path.is_symlink():
        raise RuntimeMigrationError("pinned CHECKSUMS.sha256 is missing or unsafe")
    checksum_bytes = checksum_path.read_bytes()
    actual_digest = sha256_bytes(checksum_bytes)
    if actual_digest != EXPECTED_CHECKSUMS_SHA256:
        raise RuntimeMigrationError(
            "CHECKSUMS.sha256 identity changed: "
            f"expected {EXPECTED_CHECKSUMS_SHA256}, found {actual_digest}"
        )

    values: dict[str, str] = {}
    for line in checksum_bytes.decode("utf-8").splitlines():
        try:
            digest_value, relative = line.split("  ", 1)
        except ValueError as exc:
            raise RuntimeMigrationError("invalid checksum manifest line") from exc
        if relative in values:
            raise RuntimeMigrationError(f"duplicate checksum path: {relative}")
        values[relative] = digest_value
    return values


def render_runtime_migrations(package_root: Path, output_root: Path) -> dict[str, object]:
    package_root = package_root.resolve(strict=True)
    if not package_root.is_dir() or package_root.is_symlink():
        raise RuntimeMigrationError("package root must be a real directory")
    if output_root.exists() or output_root.is_symlink():
        raise RuntimeMigrationError("output root must not already exist")
    if not output_root.parent.is_dir() or output_root.parent.is_symlink():
        raise RuntimeMigrationError("output parent must be a real directory")

    checksums = parse_checksums(package_root)
    source_root = package_root / "database" / "migrations"
    source_names = tuple(path.name for path in sorted(source_root.glob("V*.sql")))
    if source_names != EXPECTED_MIGRATIONS:
        raise RuntimeMigrationError(
            f"migration inventory changed: expected {EXPECTED_MIGRATIONS}, found {source_names}"
        )

    rendered: dict[str, bytes] = {}
    for name in EXPECTED_MIGRATIONS:
        source_path = source_root / name
        if not source_path.is_file() or source_path.is_symlink():
            raise RuntimeMigrationError(f"migration is missing or unsafe: {name}")
        source_bytes = source_path.read_bytes()
        checksum_key = f"database/migrations/{name}"
        expected_digest = checksums.get(checksum_key)
        actual_digest = sha256_bytes(source_bytes)
        if expected_digest is None or actual_digest != expected_digest:
            raise RuntimeMigrationError(
                f"migration checksum mismatch for {name}: "
                f"expected {expected_digest}, found {actual_digest}"
            )

        output_bytes = source_bytes
        if name == PATCHED_MIGRATION:
            if actual_digest != EXPECTED_PATCH_SOURCE_SHA256:
                raise RuntimeMigrationError("V020 source digest is not the pinned input")
            for old, new in PATCHES:
                if output_bytes.count(old) != 1:
                    raise RuntimeMigrationError(
                        f"V020 compatibility anchor count changed: {old!r}"
                    )
                output_bytes = output_bytes.replace(old, new)
            output_digest = sha256_bytes(output_bytes)
            if output_digest != EXPECTED_PATCH_OUTPUT_SHA256:
                raise RuntimeMigrationError(
                    "V020 compatibility output digest changed: "
                    f"expected {EXPECTED_PATCH_OUTPUT_SHA256}, found {output_digest}"
                )
        rendered[name] = output_bytes

    output_root.mkdir(mode=0o700)
    for name, content in rendered.items():
        target = output_root / name
        target.write_bytes(content)
        target.chmod(0o600)

    return {
        "migration_count": len(rendered),
        "patched_migration": PATCHED_MIGRATION,
        "source_sha256": EXPECTED_PATCH_SOURCE_SHA256,
        "output_sha256": EXPECTED_PATCH_OUTPUT_SHA256,
        "repair": "partition run_event and session_event by tenant_id",
        "production_authorized": False,
        "certification": "NOT_CERTIFIED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = render_runtime_migrations(args.package_root, args.output_root)
    except (OSError, UnicodeError, RuntimeMigrationError) as exc:
        print(f"runtime migration compatibility render failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
