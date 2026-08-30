"""Validate the attached PI Harness archive without executing package files."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "skills/subskills/elmos-pi-harness-architecture-v5.1.0.zip"
PACKAGE_ROOT = ROOT / "packages/pi-harness"
EXPECTED_ARCHIVE_SHA256 = (
    "8d600342ab0652e23aef80ef72583dfa4cbe01db7dc49b7d339dd40aa285c75c"
)
EXPECTED_ARCHIVE_BYTES = 425_097
EXPECTED_ARCHIVE_ENTRIES = 798
EXPECTED_UNCOMPRESSED_BYTES = 581_309
MAX_ENTRIES = 2_000
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024

REQUIRED_IMPLEMENTATION_MEMBERS = frozenset(
    {
        "Makefile",
        "README.md",
        "api/openapi.yaml",
        "deploy/Dockerfile",
        "deploy/requirements-production.in",
        "deploy/requirements-production.lock",
        "deploy/runtime-architecture-contract.json",
        "deploy/terraform/aws/.terraform.lock.hcl",
        "deploy/terraform/aws/main.tf",
        "deploy/terraform/aws/outputs.tf",
        "deploy/terraform/aws/variables.tf",
        "deploy/terraform/aws/versions.tf",
        "docs/COMPLETION_PLAN.md",
        "docs/EXTERNAL_QUALIFICATION_RUNBOOK.md",
        "docs/TEST_PLAN.md",
        "manifest.json",
        "pyproject.toml",
        "schemas/authority-snapshot.schema.json",
        "schemas/external-gate-result.schema.json",
        "schemas/immutable-evidence-s3.schema.json",
        "schemas/release-candidate.schema.json",
        "schemas/signed-verification.schema.json",
        "schemas/task-create.schema.json",
        "schemas/tool-result.schema.json",
        "schemas/verifier-trust-store.schema.json",
        "sql/001_pi_harness.sql",
        "sql/002_pi_harness_runtime.sql",
        "src/elmos_pi_harness/__init__.py",
        "src/elmos_pi_harness/__main__.py",
        "src/elmos_pi_harness/acceptance.py",
        "src/elmos_pi_harness/adapters.py",
        "src/elmos_pi_harness/agent.py",
        "src/elmos_pi_harness/api.py",
        "src/elmos_pi_harness/artifacts.py",
        "src/elmos_pi_harness/benchmark.py",
        "src/elmos_pi_harness/canonical.py",
        "src/elmos_pi_harness/cli.py",
        "src/elmos_pi_harness/context.py",
        "src/elmos_pi_harness/deployment.py",
        "src/elmos_pi_harness/disaster_recovery.py",
        "src/elmos_pi_harness/effects.py",
        "src/elmos_pi_harness/environment.py",
        "src/elmos_pi_harness/evidence.py",
        "src/elmos_pi_harness/executor.py",
        "src/elmos_pi_harness/external_gates.py",
        "src/elmos_pi_harness/history.py",
        "src/elmos_pi_harness/identity.py",
        "src/elmos_pi_harness/immutable_evidence.py",
        "src/elmos_pi_harness/independent_verifier.py",
        "src/elmos_pi_harness/lifecycle.py",
        "src/elmos_pi_harness/models.py",
        "src/elmos_pi_harness/multi_agent.py",
        "src/elmos_pi_harness/persistence.py",
        "src/elmos_pi_harness/policy.py",
        "src/elmos_pi_harness/postgres.py",
        "src/elmos_pi_harness/production.py",
        "src/elmos_pi_harness/protocol.py",
        "src/elmos_pi_harness/provider.py",
        "src/elmos_pi_harness/qualification.py",
        "src/elmos_pi_harness/repair.py",
        "src/elmos_pi_harness/routing.py",
        "src/elmos_pi_harness/runtime.py",
        "src/elmos_pi_harness/sandbox.py",
        "src/elmos_pi_harness/scheduler.py",
        "src/elmos_pi_harness/telemetry.py",
        "src/elmos_pi_harness/temporal.py",
        "src/elmos_pi_harness/temporal_activities.py",
        "src/elmos_pi_harness/temporal_workflows.py",
        "src/elmos_pi_harness/tool_runtime.py",
        "src/elmos_pi_harness/transformations.py",
        "src/elmos_pi_harness/verification.py",
        "tests/test_api.py",
        "tests/test_core.py",
        "tests/test_epics.py",
        "tests/test_external_gates.py",
        "tests/test_identity_integration.py",
        "tests/test_immutable_evidence.py",
        "tests/test_postgres_integration.py",
        "tests/test_production_boundaries.py",
        "tests/test_runtime_edges.py",
        "tests/test_sandbox.py",
        "tests/test_temporal_integration.py",
    }
)

REQUIRED_CAPABILITIES = frozenset(
    {
        "environment-owned authority and immutable snapshots",
        "executor generation fencing",
        "durable workspace leases and checkpoint-gated takeover",
        "protocol capability negotiation",
        "typed tool-result transport",
        "PostgreSQL 16+ pooled durable store, digest-locked migrations, RLS and managed artifacts",
        "Temporal TLS client, versioned workflow worker, cancellable signals, durable idempotent activity, generation fencing and replay runner",
        "approval-bound AWS provider operations with unknown-result identity recovery, reconciliation, rollback and destroy",
        "OIDC JWKS identity plus verified mTLS SPIFFE workload binding",
        "Ed25519 independent-verifier trust store, revocation, expiry and anti-self-verification",
        "streaming encrypted backup capture, pinned toolchain integrity, exact isolated restore target and RPO/RTO rehearsal",
        "executable customer journeys with exact customer identity, trust-domain and run-digest signed acceptance",
        "digest-bound crash-safe canary, SLO observation, promotion, rollback and provider-identity reconciliation controller",
        "frozen-RC append-only external gate ledger with content-addressed evidence, live trust-store revalidation and role-separated acceptance",
        "create-only KMS-encrypted S3 Object Lock evidence archive with version-bound receipts and unknown-result reconciliation",
        "conservative evidence/certification state",
    }
)


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and "" not in path.parts
        and "\\" not in name
    )


def _fail(message: str) -> None:
    raise SystemExit(message)


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _fail(f"invalid JSON document {path}: {exc}")
    if not isinstance(value, dict):
        _fail(f"JSON document must contain an object: {path}")
    return value


def validate_implementation(package_root: Path = PACKAGE_ROOT) -> dict[str, object]:
    if not package_root.is_dir() or package_root.is_symlink():
        _fail(f"implementation root is missing or unsafe: {package_root}")
    missing: list[str] = []
    unsafe: list[str] = []
    for member in sorted(REQUIRED_IMPLEMENTATION_MEMBERS):
        target = package_root / member
        if not target.is_file():
            missing.append(member)
        elif target.is_symlink():
            unsafe.append(member)
    if missing:
        _fail("implementation is missing required members: " + ", ".join(missing))
    if unsafe:
        _fail("implementation contains symlink members: " + ", ".join(unsafe))

    manifest = _read_json(package_root / "manifest.json")
    expected_manifest = {
        "name": "elmos-pi-harness",
        "version": "5.1.0",
        "source_package": "elmos-pi-harness-architecture-v5.1.0",
        "source_archive_sha256": "sha256:" + EXPECTED_ARCHIVE_SHA256,
        "source_archive_bytes": EXPECTED_ARCHIVE_BYTES,
        "source_archive_executed": False,
        "implementation_status": "CODE_COMPLETE_EXTERNAL_EVIDENCE_PENDING",
        "external_evidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "certified": False,
    }
    for key, expected in expected_manifest.items():
        if manifest.get(key) != expected:
            _fail(
                f"implementation manifest {key} mismatch: "
                f"expected={expected!r} actual={manifest.get(key)!r}"
            )
    implemented = manifest.get("implemented")
    if not isinstance(implemented, list) or any(
        not isinstance(item, str) for item in implemented
    ):
        _fail("implementation manifest implemented must be a string array")
    missing_capabilities = sorted(REQUIRED_CAPABILITIES - set(implemented))
    if missing_capabilities:
        _fail(
            "implementation manifest is missing required capabilities: "
            + ", ".join(missing_capabilities)
        )

    project = tomllib.loads((package_root / "pyproject.toml").read_text("utf-8"))
    metadata = project.get("project", {})
    if not isinstance(metadata, dict) or (
        metadata.get("name"),
        metadata.get("version"),
    ) != ("elmos-pi-harness", "5.1.0"):
        _fail("pyproject identity does not match elmos-pi-harness 5.1.0")
    extras = metadata.get("optional-dependencies", {})
    if not isinstance(extras, dict) or not {
        "api",
        "postgres",
        "temporal",
        "identity",
        "cloud",
        "production",
        "dev",
    }.issubset(extras):
        _fail("pyproject is missing required optional dependency profiles")

    schema_count = 0
    for path in sorted((package_root / "schemas").glob("*.schema.json")):
        schema = _read_json(path)
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            _fail(f"schema does not declare JSON Schema 2020-12: {path}")
        schema_count += 1
    if schema_count != 8:
        _fail(f"expected 8 JSON schemas, found {schema_count}")

    for relative in (
        "README.md",
        "docs/COMPLETION_PLAN.md",
        "docs/EXTERNAL_QUALIFICATION_RUNBOOK.md",
        "docs/TEST_PLAN.md",
    ):
        text = (package_root / relative).read_text(encoding="utf-8")
        if "NOT_RUN" not in text or "NOT_CERTIFIED" not in text:
            _fail(f"status boundary is missing from {relative}")

    return {
        "root": str(package_root),
        "required_members": len(REQUIRED_IMPLEMENTATION_MEMBERS),
        "required_capabilities": len(REQUIRED_CAPABILITIES),
        "schemas": schema_count,
        "implementation_status": manifest["implementation_status"],
        "external_evidence": manifest["external_evidence"],
        "certification": manifest["certification"],
    }


def validate(
    archive: Path = ARCHIVE, package_root: Path = PACKAGE_ROOT
) -> dict[str, object]:
    if not archive.is_file() or archive.is_symlink():
        _fail(f"SOURCE_PACKAGE_ABSENT_OR_UNSAFE={archive}")
    raw = archive.read_bytes()
    if len(raw) != EXPECTED_ARCHIVE_BYTES:
        _fail(
            "archive byte count mismatch: "
            f"expected={EXPECTED_ARCHIVE_BYTES} actual={len(raw)}"
        )
    archive_sha256 = hashlib.sha256(raw).hexdigest()
    if archive_sha256 != EXPECTED_ARCHIVE_SHA256:
        _fail(
            "archive digest mismatch: "
            f"expected={EXPECTED_ARCHIVE_SHA256} actual={archive_sha256}"
        )
    with zipfile.ZipFile(archive) as package:
        infos = package.infolist()
        if len(infos) > MAX_ENTRIES:
            _fail("archive has too many entries")
        if len(infos) != EXPECTED_ARCHIVE_ENTRIES:
            _fail(
                "archive entry count mismatch: "
                f"expected={EXPECTED_ARCHIVE_ENTRIES} actual={len(infos)}"
            )
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            _fail("archive contains duplicate member names")
        if any(not _safe_name(name) for name in names):
            _fail("archive contains an unsafe path")
        total = 0
        for info in infos:
            total += info.file_size
            if info.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_BYTES:
                _fail("archive exceeds configured size limit")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                _fail(f"archive contains a symlink member: {info.filename}")
        if total != EXPECTED_UNCOMPRESSED_BYTES:
            _fail(
                "archive uncompressed byte count mismatch: "
                f"expected={EXPECTED_UNCOMPRESSED_BYTES} actual={total}"
            )
        prefix = "elmos-pi-harness-architecture/"
        manifest_name = prefix + "manifest.json"
        required = {prefix + "SKILL.md", prefix + "README.md", manifest_name}
        if not required.issubset(names):
            _fail("archive is missing its required package metadata")
        manifest = json.loads(package.read(manifest_name).decode("utf-8"))
        if (
            manifest.get("name") != "elmos-pi-harness-architecture"
            or manifest.get("version") != "5.1.0"
        ):
            _fail("archive manifest identity does not match the requested package")
    implementation = validate_implementation(package_root)
    return {
        "archive": str(archive),
        "sha256": archive_sha256,
        "entries": len(names),
        "uncompressed_bytes": total,
        "executed": False,
        "status": "VALIDATED_AS_UNTRUSTED_SOURCE",
        "implementation": implementation,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(validate(args.archive), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
