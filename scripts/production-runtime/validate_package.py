#!/usr/bin/env python3
"""Fail-closed static validator for the production-runtime source package.

The package is specification material.  This validator reads bytes and parses
declarative formats only; it never imports, executes, installs, or shells out
to anything contained in the archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import stat
import sys
import zipfile
from pathlib import Path


ARCHIVE_SHA256 = "7685f34453d896747c177b9299c01f1a101c94a1ea4808ae6dc92fec51203c37"
PACKAGE_ROOT = "elmos-production-runtime-skillpack-v1.2.0"
EXPECTED_FILE_COUNT = 62
EXPECTED_WORKLOADS = {
    "repository-language-conversion-v1": "LANGUAGE_CONVERSION",
    "multilingual-project-generation-v1": "PROJECT_GENERATION",
    "spring-modernization-v1": "SPRING_MODERNIZATION",
    "sql-dialect-routine-conversion-v1": "SQL_CONVERSION",
}
EXPECTED_SCENARIOS = {
    "BillingReconciliation",
    "ChaosMatrix",
    "ConcurrentReserve",
    "CreditExhaustionResume",
    "DuplicateProviderCallReplay",
    "DuplicateUsage",
    "IdempotencyConflict",
    "JournalBalance",
    "LeaseExpiry",
    "PITRRestore",
    "ProjectorReplay",
    "RLSIsolation",
    "RedisLoss",
    "SchedulerRestartAtDispatching",
    "SchedulerRestartAtReserved",
    "SchedulerRestartAtReserving",
    "StaleFence",
    "StreamingUsageReconciliation",
    "TopUpReplay",
    "WorkerCrashCheckpointResume",
}


class PackageError(RuntimeError):
    pass


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def safe_relative(name: str) -> str:
    if "\\" in name or "\x00" in name:
        raise PackageError(f"unsafe archive path: {name!r}")
    normalized = posixpath.normpath(name)
    if normalized != name or normalized.startswith("../") or normalized == "..":
        raise PackageError(f"non-canonical archive path: {name!r}")
    if not normalized.startswith(PACKAGE_ROOT + "/"):
        raise PackageError(f"archive entry is outside package root: {name!r}")
    relative = normalized[len(PACKAGE_ROOT) + 1 :]
    if not relative or relative.startswith("/"):
        raise PackageError(f"invalid package-relative path: {name!r}")
    return relative


def load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise PackageError("PyYAML is required to validate declarative YAML") from exc
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except Exception as exc:  # yaml parser errors are part of validation output
        raise PackageError(f"invalid YAML: {path}: {exc}") from exc


def validate_archive(archive: Path) -> dict[str, bytes]:
    if not archive.is_file() or archive.is_symlink():
        raise PackageError(f"archive is not a regular file: {archive}")
    actual_digest = digest(archive)
    if actual_digest != ARCHIVE_SHA256:
        raise PackageError(f"archive SHA-256 mismatch: expected {ARCHIVE_SHA256}, got {actual_digest}")

    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(archive) as handle:
            if len(handle.infolist()) != EXPECTED_FILE_COUNT:
                raise PackageError(f"archive entry count mismatch: expected {EXPECTED_FILE_COUNT}, got {len(handle.infolist())}")
            for info in handle.infolist():
                relative = safe_relative(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type == stat.S_IFLNK:
                    raise PackageError(f"archive contains a symbolic link: {info.filename}")
                if info.is_dir() or file_type == stat.S_IFDIR:
                    raise PackageError(f"archive contains an unexpected directory entry: {info.filename}")
                if file_type not in (0, stat.S_IFREG):
                    raise PackageError(f"archive contains a non-regular entry: {info.filename}")
                if relative in files:
                    raise PackageError(f"duplicate archive entry: {relative}")
                content = handle.read(info)
                if len(content) != info.file_size:
                    raise PackageError(f"truncated archive entry: {info.filename}")
                files[relative] = content
    except zipfile.BadZipFile as exc:
        raise PackageError(f"invalid ZIP archive: {archive}") from exc
    return files


def validate_extracted_tree(root: Path, files: dict[str, bytes]) -> None:
    if not root.is_dir() or root.is_symlink():
        raise PackageError(f"immutable extracted root is missing or unsafe: {root}")
    expected = set(files)
    actual: set[str] = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise PackageError(f"extracted package contains a symlink: {path}")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
        elif not path.is_dir():
            raise PackageError(f"extracted package contains a special file: {path}")
    if actual != expected:
        raise PackageError(f"extracted inventory mismatch: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}")
    for relative, expected_bytes in files.items():
        actual_bytes = (root / relative).read_bytes()
        if actual_bytes != expected_bytes:
            raise PackageError(f"extracted bytes differ from archive: {relative}")


def validate_contracts(root: Path) -> None:
    for name in ("contracts/dispatch-intent.schema.json", "contracts/usage-meter-event.schema.json"):
        value = json.loads((root / name).read_text(encoding="utf-8"))
        if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema" or value.get("type") != "object":
            raise PackageError(f"contract is not a draft-2020-12 object schema: {name}")
        if not value.get("required") or not isinstance(value["properties"], dict):
            raise PackageError(f"contract has no required properties: {name}")


def validate_declarations(root: Path) -> None:
    manifest = load_yaml(root / "manifest.yaml")
    if not isinstance(manifest, dict) or manifest.get("name") != "elmos-production-runtime" or manifest.get("version") != "1.2.0":
        raise PackageError("manifest identity is not elmos-production-runtime v1.2.0")
    invariants = set(manifest.get("platform_invariants", []))
    required_invariants = {"postgres-is-authoritative", "redis-is-ephemeral-only", "tenant-isolation", "transactional-outbox", "provider-call-idempotency"}
    if not required_invariants <= invariants:
        raise PackageError(f"manifest is missing platform invariants: {sorted(required_invariants - invariants)}")

    workload_dir = root / "workload-packs"
    seen: dict[str, str] = {}
    for path in sorted(workload_dir.glob("*.yaml")):
        value = load_yaml(path)
        if not isinstance(value, dict) or not isinstance(value.get("id"), str) or not isinstance(value.get("job_type"), str):
            raise PackageError(f"invalid workload pack identity: {path}")
        stages = value.get("stages")
        if not isinstance(stages, list) or not stages or any(not isinstance(stage, str) or not stage.strip() for stage in stages):
            raise PackageError(f"workload pack has no valid ordered stages: {path}")
        seen[value["id"]] = value["job_type"]
    if seen != EXPECTED_WORKLOADS:
        raise PackageError(f"workload pack inventory mismatch: expected {EXPECTED_WORKLOADS}, got {seen}")

    scenario_dir = root / "tests" / "scenarios"
    scenarios = {path.stem for path in scenario_dir.glob("*.md")}
    if scenarios != EXPECTED_SCENARIOS:
        raise PackageError(f"scenario inventory mismatch: missing={sorted(EXPECTED_SCENARIOS - scenarios)}, extra={sorted(scenarios - EXPECTED_SCENARIOS)}")
    for path in sorted(scenario_dir.glob("*.md")):
        if not path.read_text(encoding="utf-8").strip():
            raise PackageError(f"empty production scenario: {path}")


def validate_required_content(root: Path) -> None:
    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    required_phrases = (
        "PostgreSQL",
        "Redis",
        "Dispatch Saga",
        "fencing",
        "idempotency",
        "reconciliation",
    )
    for phrase in required_phrases:
        if phrase.lower() not in skill.lower():
            raise PackageError(f"SKILL.md lost required runtime boundary: {phrase}")
    invariant_sql = (root / "tests/sql/invariants.sql").read_text(encoding="utf-8").lower()
    for phrase in ("reserved_balance", "journal", "provider_usage_id", "tenant_id"):
        if phrase not in invariant_sql:
            raise PackageError(f"invariant SQL lost required check: {phrase}")
    for name in ("deploy/helm/Chart.yaml", "deploy/helm/values.yaml", "deploy/helm/templates/network-policy.yaml", "deploy/helm/templates/worker-statefulset.yaml"):
        if not (root / name).is_file():
            raise PackageError(f"required deployment asset is missing: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", nargs="?", type=Path, default=Path("skills/subskills/elmos-production-runtime-skillpack-v1.2.0.zip"))
    parser.add_argument("--extracted-root", type=Path, default=Path("skills/elmos-production-runtime-skillpack-v1.2.0"))
    args = parser.parse_args()
    try:
        files = validate_archive(args.archive)
        validate_extracted_tree(args.extracted_root, files)
        validate_contracts(args.extracted_root)
        validate_declarations(args.extracted_root)
        validate_required_content(args.extracted_root)
    except (OSError, PackageError, json.JSONDecodeError) as exc:
        print(f"production-runtime package validation: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"production-runtime package validation: PASS ({len(files)} immutable files, sha256={ARCHIVE_SHA256})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
