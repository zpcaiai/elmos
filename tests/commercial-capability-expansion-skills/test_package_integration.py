"""Tests for Elmos Commercial Capability Expansion v2.0.0 package integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "skills/elmos-commercial-capability-expansion-skills-v2.0.0"
ARCHIVE_PATH = ROOT / "skills/subskills/elmos-commercial-capability-expansion-skills-v2.0.0.zip"
FALLBACK_ARCHIVE_PATH = ROOT / "skills/subskills/sub/elmos-commercial-capability-expansion-skills-v2.0.0.zip"
RECEIPT_PATH = ROOT / "docs/commercial-capability-expansion/QUALIFICATION_RECEIPT.json"

EXPECTED_SHA256 = "7a73cf924f4ebab3eddba327ba4feeb64b8575e39f2baf03fc53315cbc868380"
EXPECTED_BYTES = 161_254
EXPECTED_FILES = 105


def test_archive_digest_and_size():
    archive = ARCHIVE_PATH if ARCHIVE_PATH.is_file() else FALLBACK_ARCHIVE_PATH
    assert archive.is_file(), f"Archive not found: {archive}"
    data = archive.read_bytes()
    assert len(data) == EXPECTED_BYTES
    assert hashlib.sha256(data).hexdigest() == EXPECTED_SHA256


def test_extracted_directory_structure():
    assert PACKAGE_DIR.is_dir(), f"Extracted directory missing: {PACKAGE_DIR}"
    assert (PACKAGE_DIR / "manifest.json").is_file()
    assert (PACKAGE_DIR / "SKILL.md").is_file()
    assert (PACKAGE_DIR / "README.md").is_file()
    assert (PACKAGE_DIR / "schemas").is_dir()
    assert (PACKAGE_DIR / "skills").is_dir()


def test_schemas_conformance():
    schemas_dir = PACKAGE_DIR / "schemas"
    schemas = list(schemas_dir.glob("*.json"))
    assert len(schemas) >= 3
    for s in schemas:
        data = json.loads(s.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(data)


def test_dual_root_installation():
    manifest = json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))
    skills = manifest.get("skills", [])
    assert len(skills) == 85

    workspace_root = ROOT / ".agents/skills"
    runtime_root = ROOT / "agent-skills/runtime"

    # Verify master skill
    assert (workspace_root / "elmos-commercial-capability-expansion/SKILL.md").is_file()
    assert (runtime_root / "elmos-commercial-capability-expansion/SKILL.md").is_file()

    # Verify all 85 skills
    for s in skills:
        sid = s["id"]
        ws_file = workspace_root / sid / "SKILL.md"
        rt_file = runtime_root / sid / "SKILL.md"
        assert ws_file.is_file(), f"Missing in .agents/skills: {sid}"
        assert rt_file.is_file(), f"Missing in agent-skills/runtime: {sid}"


def test_qualification_receipt():
    assert RECEIPT_PATH.is_file(), f"Missing qualification receipt: {RECEIPT_PATH}"
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["package_id"] == "elmos-commercial-capability-expansion-skills-v2.0.0"
    assert receipt["archive_sha256"] == EXPECTED_SHA256
    assert receipt["skill_count"] == 85
    assert receipt["compliance"]["dual_root_installed"] is True
    assert receipt["compliance"]["immutable_extraction"] is True
