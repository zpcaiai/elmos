#!/usr/bin/env python3
"""Safely integrate and independently qualify the Elmos Pricing & Billing v1.0.0 package.

Extracts the pinned archive, verifies internal SHA256 checksums, installs the 18
pricing & billing skills into both workspace and runtime skill roots, and generates
a qualification receipt without executing untrusted archive scripts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORY = "elmos-pricing-billing-skills-v1.0.0"
PACKAGE_ID = "elmos-pricing-billing-skills-v1.0.0"
PACKAGE_NAME = "elmos-pricing-billing-skills"
PACKAGE_VERSION = "1.0.0"

PRIMARY_ARCHIVE_RELATIVE = Path("skills/subskills") / f"{PACKAGE_DIRECTORY}.zip"
SOURCE_RELATIVE = Path("skills") / PACKAGE_DIRECTORY
ENGINE_RELATIVE = Path("engines/pricing-billing-engine")
RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")

EXPECTED_ARCHIVE_SHA256 = "9f7440b69a82a52172a1f62da915d96cfa4e0326dc04a305603c76001c8e88bc"
EXPECTED_ARCHIVE_BYTES = 246_184
EXPECTED_SKILL_COUNT = 18


class IntegrationError(RuntimeError):
    pass


def fail(message: str) -> None:
    raise IntegrationError(message)


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def resolve_archive() -> Path:
    p1 = ROOT / PRIMARY_ARCHIVE_RELATIVE
    if p1.is_file():
        return p1
    fail(f"Archive missing at {PRIMARY_ARCHIVE_RELATIVE}")


def verify_archive(path: Path) -> str:
    data = path.read_bytes()
    if len(data) != EXPECTED_ARCHIVE_BYTES:
        fail(f"archive byte count mismatch: expected {EXPECTED_ARCHIVE_BYTES}, got {len(data)}")
    digest = digest_bytes(data)
    if digest != EXPECTED_ARCHIVE_SHA256:
        fail(f"archive digest mismatch: expected {EXPECTED_ARCHIVE_SHA256}, got {digest}")
    return digest


def extract_archive_safely(archive_path: Path, target_dir: Path) -> None:
    import zipfile
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            target_path = target_dir / member.filename
            resolved = target_path.resolve()
            if not resolved.is_relative_to(target_dir.resolve()):
                fail(f"Zip extraction path traversal rejected: {member.filename}")
            if member.is_dir():
                resolved.mkdir(parents=True, exist_ok=True)
            else:
                resolved.parent.mkdir(parents=True, exist_ok=True)
                resolved.write_bytes(zf.read(member.filename))


def verify_controlled_files(source_dir: Path) -> dict[str, str]:
    cf_path = source_dir / "CHECKSUMS.sha256"
    if not cf_path.is_file():
        fail("missing CHECKSUMS.sha256 in source")
    rows = cf_path.read_text(encoding="utf-8").splitlines()
    checked: dict[str, str] = {}
    for line in rows:
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            fail(f"malformed checksum line: {line}")
        digest, rel = parts
        target = source_dir / rel
        if not target.is_file():
            fail(f"missing controlled file: {rel}")
        actual = digest_bytes(target.read_bytes())
        if actual != digest:
            fail(f"checksum mismatch for {rel}: expected {digest}, got {actual}")
        checked[rel] = digest
    return checked


def install_dual_root_skills(source_dir: Path) -> int:
    source_root = source_dir / PACKAGE_DIRECTORY if (source_dir / PACKAGE_DIRECTORY).is_dir() else source_dir
    skills_dir = source_root / "skills"
    
    workspace_skills_root = ROOT / WORKSPACE_SKILLS_RELATIVE
    runtime_skills_root = ROOT / RUNTIME_SKILLS_RELATIVE
    workspace_skills_root.mkdir(parents=True, exist_ok=True)
    runtime_skills_root.mkdir(parents=True, exist_ok=True)
    
    installed_count = 0
    for skill_subdir in sorted(skills_dir.iterdir()):
        if not skill_subdir.is_dir():
            continue
        skill_name = skill_subdir.name
        for root_dest in (workspace_skills_root, runtime_skills_root):
            dest = root_dest / skill_name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(skill_subdir, dest)
        installed_count += 1

    return installed_count


def generate_local_qualification(archive_digest: str, skill_count: int) -> dict[str, Any]:
    qualification_dir = ROOT / ENGINE_RELATIVE / "qualification"
    qualification_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = qualification_dir / "local-qualification.json"

    receipt = {
        "schema_version": "elmos.pricing-billing.qualification.v1",
        "package_id": PACKAGE_ID,
        "package_version": PACKAGE_VERSION,
        "archive_sha256": archive_digest,
        "qualification_state": "QUALIFIED_SELF_ATTESTED",
        "evidence_status": "LOCAL_EXECUTED_SELF_ATTESTED",
        "customer_evidence_status": "NOT_RUN",
        "external_evidence_status": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
        "side_effects_authorized": False,
        "qualified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skills_count": skill_count,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(receipt_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-only", action="store_true", help="Extract archive without installing")
    parser.add_argument("--validate-only", "--check", action="store_true", dest="validate_only", help="Validate extracted source")
    parser.add_argument("--write", action="store_true", help="Extract, validate, install, and generate qualification receipt")
    args = parser.parse_args()

    archive_path = resolve_archive()
    archive_digest = verify_archive(archive_path)
    print(f"Archive verified: {archive_path.name} (SHA-256: {archive_digest})")

    source_dir = ROOT / SOURCE_RELATIVE
    if args.write or args.extract_only or not source_dir.is_dir():
        extract_archive_safely(archive_path, source_dir)
        print(f"Archive extracted to: {source_dir}")

    controlled_source = source_dir / PACKAGE_DIRECTORY if (source_dir / PACKAGE_DIRECTORY).is_dir() else source_dir
    checked_files = verify_controlled_files(controlled_source)
    print(f"CHECKSUMS.sha256 verified: {len(checked_files)} files checked")

    skills_dir = controlled_source / "skills"
    skill_count = len([p for p in skills_dir.iterdir() if p.is_dir()])
    if skill_count != EXPECTED_SKILL_COUNT:
        fail(f"skill count mismatch: expected {EXPECTED_SKILL_COUNT}, got {skill_count}")
    print(f"Validation passed: {skill_count} pricing & billing skills")

    if args.write or not args.validate_only:
        installed = install_dual_root_skills(controlled_source)
        print(f"Dual-root installed: {installed} skills to .agents/skills/ and agent-skills/runtime/")
        receipt = generate_local_qualification(archive_digest, skill_count)
        print(f"Qualification receipt generated: {receipt['qualification_state']}")

    print(json.dumps({"status": "PASS", "package": PACKAGE_ID, "skills": skill_count}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
