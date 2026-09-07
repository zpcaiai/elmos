"""Integration tests for ELMOS Polyglot Repository Semantic Compiler Skills v3.0.0."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = ROOT / "skills/elmos-polyglot-skills-v3.0.0-semantic-assurance"
ARCHIVE_PATH = ROOT / "skills/subskills/sub/elmos-polyglot-skills-v3.0.0-semantic-assurance.zip"
FALLBACK_ARCHIVE_PATH = ROOT / "skills/subskills/elmos-polyglot-skills-v3.0.0-semantic-assurance.zip"
RECEIPT_PATH = ROOT / "docs/polyglot-semantic-assurance/QUALIFICATION_RECEIPT.json"

EXPECTED_SHA256 = "7bce369fdeb9b3f86753c353e2d72bb53bb9e91e7368abc7c24a26c132d1db17"
EXPECTED_BYTES = 1_502_151
EXPECTED_SKILLS = 300


def test_archive_digest_and_size():
    archive = ARCHIVE_PATH if ARCHIVE_PATH.is_file() else FALLBACK_ARCHIVE_PATH
    assert archive.is_file(), f"Archive not found: {archive}"
    data = archive.read_bytes()
    assert len(data) == EXPECTED_BYTES
    assert hashlib.sha256(data).hexdigest() == EXPECTED_SHA256


def test_extracted_directory_structure():
    assert PACKAGE_DIR.is_dir(), f"Extracted directory missing: {PACKAGE_DIR}"
    assert (PACKAGE_DIR / "manifest.json").is_file()
    assert (PACKAGE_DIR / "README.md").is_file()
    assert (PACKAGE_DIR / "schemas").is_dir()
    assert (PACKAGE_DIR / "agent-skills/runtime").is_dir()


def test_schemas_conformance():
    schemas_dir = PACKAGE_DIR / "schemas"
    schemas = list(schemas_dir.glob("*.json"))
    assert len(schemas) >= 10
    for s in schemas:
        data = json.loads(s.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(data)


def test_dual_root_installation():
    manifest = json.loads((PACKAGE_DIR / "manifest.json").read_text(encoding="utf-8"))
    skills = manifest.get("skills", [])
    assert len(skills) == EXPECTED_SKILLS

    workspace_root = ROOT / ".agents/skills"
    runtime_root = ROOT / "agent-skills/runtime"

    for s in skills:
        name = s["name"]
        ws_file = workspace_root / name / "SKILL.md"
        rt_file = runtime_root / name / "SKILL.md"
        assert ws_file.is_file(), f"Missing in .agents/skills: {name}"
        assert rt_file.is_file(), f"Missing in agent-skills/runtime: {name}"


def test_qualification_receipt():
    assert RECEIPT_PATH.is_file(), f"Missing qualification receipt: {RECEIPT_PATH}"
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["package_id"] == "elmos-polyglot-skills-v3.0.0-semantic-assurance"
    assert receipt["archive_sha256"] == EXPECTED_SHA256
    assert receipt["skill_count"] == EXPECTED_SKILLS
    assert len(receipt["batches_breakdown"]) == 18
    assert receipt["compliance"]["dual_root_installed"] is True
    assert receipt["compliance"]["immutable_extraction"] is True
