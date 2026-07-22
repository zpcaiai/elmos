#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BASE_PACKAGE = ROOT / "elmos-project-synthesis-batch46-60"
EXTENSION_PACKAGE = ROOT / "elmos-project-synthesis-batch61-65"
POLYGLOT_PACKAGE = ROOT / "elmos-codex-skills-batch66-80-complete"
LANGUAGE_PACKAGE = ROOT / "elmos-language-packs-batch81-95-complete"
LANGUAGE_INSTALL_MANIFEST = ROOT / "docs/language-packs-batch81-95/installed-manifest.json"
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
errors: list[str] = []


def require(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest_path = BASE_PACKAGE / "manifest.json"
extension_manifest_path = EXTENSION_PACKAGE / "package-manifest.json"
polyglot_manifest_path = POLYGLOT_PACKAGE / "manifest.json"
language_manifest_path = LANGUAGE_PACKAGE / "package-manifest.json"
require(manifest_path.is_file(), "canonical Batch 46-60 project-synthesis manifest is missing")
require(extension_manifest_path.is_file(), "canonical Batch 61-65 project-synthesis manifest is missing")
require(polyglot_manifest_path.is_file(), "canonical Batch 66-80 project-synthesis manifest is missing")
require(language_manifest_path.is_file(), "canonical Batch 81-95 Language Pack manifest is missing")
manifest = load_json(manifest_path) if manifest_path.is_file() else {}
extension_manifest = load_json(extension_manifest_path) if extension_manifest_path.is_file() else {}
polyglot_manifest = load_json(polyglot_manifest_path) if polyglot_manifest_path.is_file() else {}
language_manifest = load_json(language_manifest_path) if language_manifest_path.is_file() else {}

base_skills = sorted((BASE_PACKAGE / "skills").glob("batch-*/*.md"))
extension_skills = sorted((EXTENSION_PACKAGE / "skills").glob("batch-*/*.md"))
polyglot_skills = sorted((POLYGLOT_PACKAGE / "skills").glob("batch-*/*.md"))
language_skills = sorted((LANGUAGE_PACKAGE / "skills").glob("batch-*/*/SKILL.md"))
skills = base_skills + extension_skills + polyglot_skills
schemas = (
    sorted((BASE_PACKAGE / "schemas").glob("batch-*/*.json"))
    + sorted((EXTENSION_PACKAGE / "schemas").glob("*.json"))
    + sorted((POLYGLOT_PACKAGE / "schemas").glob("*.json"))
    + sorted((LANGUAGE_PACKAGE / "schemas").glob("*.json"))
)

require(manifest.get("engine") == "elmos.project-synthesis", "manifest engine is not elmos.project-synthesis")
require(manifest.get("skillCount") == 170, "manifest must declare exactly 170 Project Synthesis skills")
require(extension_manifest.get("package") == "elmos-project-synthesis-batch-61-65", "extension package identity is invalid")
require(extension_manifest.get("skills") == 52, "extension manifest must declare exactly 52 skills")
require(polyglot_manifest.get("package") == "elmos-codex-skills-batch66-80-complete", "Batch 66-80 package identity is invalid")
require(polyglot_manifest.get("skill_count") == 195, "Batch 66-80 package must declare exactly 195 Skills")
require(polyglot_manifest.get("id_range") == ["PG223", "PG417"], "Batch 66-80 ID range must be PG223-PG417")
require(polyglot_manifest.get("batches") == list(range(66, 81)), "Batch 66-80 package coverage is invalid")
require(language_manifest.get("package") == "elmos-language-packs-batch81-95-complete", "Batch 81-95 Language Pack identity is invalid")
require(language_manifest.get("skills") == 180, "Batch 81-95 package must declare exactly 180 Skills")
require(language_manifest.get("skill_id_range") == ["PG223", "PG402"], "Batch 81-95 source ID range must remain package-local PG223-PG402")
require(language_manifest.get("batches") == list(range(81, 96)), "Batch 81-95 package coverage is invalid")
require(len(skills) == 417, f"expected 417 Project Synthesis skill specifications, found {len(skills)}")
require(len(language_skills) == 180, f"expected 180 package-local Language Pack specifications, found {len(language_skills)}")
require(len(schemas) == 41, f"expected 41 retained Project Synthesis and Language Pack schemas, found {len(schemas)}")

# The Batch 61-65 archive is retained byte-for-byte as a proposed specification
# package. Verify both of its independent content manifests before using it as
# routing input; neither manifest is runtime or production evidence.
extension_entries = extension_manifest.get("files", [])
require(isinstance(extension_entries, list) and len(extension_entries) == 75, "Batch 61-65 package manifest must bind exactly 75 payload files")
extension_listed_paths: set[str] = set()
for entry in extension_entries if isinstance(extension_entries, list) else []:
    relative = entry.get("path") if isinstance(entry, dict) else None
    path = EXTENSION_PACKAGE / relative if isinstance(relative, str) else EXTENSION_PACKAGE
    require(isinstance(relative, str) and path.is_file(), f"Batch 61-65 manifest file is missing: {relative}")
    if isinstance(relative, str):
        require(relative not in extension_listed_paths, f"Batch 61-65 manifest duplicates {relative}")
        extension_listed_paths.add(relative)
    if isinstance(relative, str) and path.is_file():
        require(path.stat().st_size == entry.get("size_bytes"), f"Batch 61-65 file size mismatch: {relative}")
        require(sha256(path) == entry.get("sha256"), f"Batch 61-65 file digest mismatch: {relative}")
extension_payload = {
    path.relative_to(EXTENSION_PACKAGE).as_posix()
    for path in EXTENSION_PACKAGE.rglob("*")
    if path.is_file()
} - {"SHA256SUMS.txt", "VALIDATION_REPORT.json", "package-manifest.json"}
require(extension_listed_paths == extension_payload, "Batch 61-65 package manifest file set is incomplete or overbroad")

extension_sums_path = EXTENSION_PACKAGE / "SHA256SUMS.txt"
require(extension_sums_path.is_file(), "Batch 61-65 SHA256SUMS.txt is missing")
sum_paths: set[str] = set()
if extension_sums_path.is_file():
    for line_number, line in enumerate(extension_sums_path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            errors.append(f"Batch 61-65 invalid SHA256SUMS line {line_number}")
            continue
        relative = parts[1].lstrip("*")
        path = EXTENSION_PACKAGE / relative
        require(relative not in sum_paths, f"Batch 61-65 SHA256SUMS duplicates {relative}")
        sum_paths.add(relative)
        require(path.is_file(), f"Batch 61-65 SHA256SUMS file is missing: {relative}")
        if path.is_file():
            require(sha256(path) == parts[0], f"Batch 61-65 SHA256SUMS digest mismatch: {relative}")
expected_sum_paths = extension_payload | {"package-manifest.json"}
require(sum_paths == expected_sum_paths, "Batch 61-65 SHA256SUMS file set is incomplete or overbroad")

extension_index = load_json(EXTENSION_PACKAGE / "index.json")
extension_index_skills = extension_index.get("skills", []) if isinstance(extension_index, dict) else []
extension_batch_entries: list[dict[str, Any]] = []
for batch in range(61, 66):
    batch_manifest_path = EXTENSION_PACKAGE / f"batch-{batch}-manifest.json"
    require(batch_manifest_path.is_file(), f"Batch {batch} Project Synthesis manifest is missing")
    if not batch_manifest_path.is_file():
        continue
    batch_manifest = load_json(batch_manifest_path)
    entries = batch_manifest.get("skills", [])
    require(batch_manifest.get("batch") == batch, f"Batch {batch} Project Synthesis manifest identity is invalid")
    require(isinstance(entries, list) and len(entries) == batch_manifest.get("skill_count"), f"Batch {batch} Project Synthesis manifest count is invalid")
    extension_batch_entries.extend(entries if isinstance(entries, list) else [])
require(len(extension_batch_entries) == 52, "Batch 61-65 manifests must declare exactly 52 Skills")
require(extension_index_skills == extension_batch_entries, "Batch 61-65 index differs from Batch manifests")
expected_extension_ids = [f"PG{number:03d}" for number in range(171, 223)]
require([entry.get("id") for entry in extension_batch_entries] == expected_extension_ids, "Batch 61-65 manifest IDs must be PG171-PG222")
for entry in extension_batch_entries:
    relative = entry.get("path") if isinstance(entry, dict) else None
    path = EXTENSION_PACKAGE / relative if isinstance(relative, str) else EXTENSION_PACKAGE
    require(isinstance(relative, str) and path.is_file(), f"Batch 61-65 Skill file is missing: {relative}")
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8")
    id_match = re.search(r"^id:\s*(PG\d{3})\s*$", text, re.MULTILINE)
    name_match = re.search(r"^name:\s*([a-z0-9-]+)\s*$", text, re.MULTILINE)
    status_match = re.search(r"^status:\s*([a-z0-9-]+)\s*$", text, re.MULTILINE)
    require(id_match is not None and id_match.group(1) == entry.get("id"), f"Batch 61-65 Skill ID mismatch: {relative}")
    require(name_match is not None and name_match.group(1) == entry.get("name"), f"Batch 61-65 Skill name mismatch: {relative}")
    require(status_match is not None and status_match.group(1) == "proposed", f"Batch 61-65 specification status must remain proposed: {relative}")
    dependencies = entry.get("depends_on", [])
    require(isinstance(dependencies, list) and all(re.fullmatch(r"PG\d{3}", value or "") and 1 <= int(value[2:]) <= 222 for value in dependencies), f"Batch 61-65 dependency range is invalid: {relative}")

for entry in polyglot_manifest.get("files", []):
    relative = entry.get("path") if isinstance(entry, dict) else None
    path = POLYGLOT_PACKAGE / relative if isinstance(relative, str) else POLYGLOT_PACKAGE
    require(isinstance(relative, str) and path.is_file(), f"Batch 66-80 manifest file is missing: {relative}")
    if isinstance(relative, str) and path.is_file():
        require(path.stat().st_size == entry.get("size_bytes"), f"Batch 66-80 file size mismatch: {relative}")
        require(sha256(path) == entry.get("sha256"), f"Batch 66-80 file digest mismatch: {relative}")

ids: list[str] = []
batches: Counter[int] = Counter()
numbered_headings = {
    "## 1. Objective",
    "## 3. Inputs",
    "## 4. Outputs",
    "## 6. Workflow",
    "## 12. Evidence Contract",
    "## 14. Unit Tests",
    "## 17. Acceptance Criteria",
    "## 18. Definition of Done",
}
polyglot_headings = {
    "## Objective",
    "## Inputs",
    "## Outputs",
    "## Workflow",
    "## Required Tests",
    "## Verification",
    "## Evidence Contract",
    "## Definition of Done",
}
for path in skills:
    text = path.read_text(encoding="utf-8")
    id_match = re.search(r"^\s*id:\s*(PG\d{3})\s*$", text, re.MULTILINE)
    batch_match = re.search(r"batch-(\d+)", str(path.parent))
    require(id_match is not None, f"missing PG id in {path.relative_to(ROOT)}")
    require(batch_match is not None, f"missing batch number in {path.relative_to(ROOT)}")
    if id_match:
        ids.append(id_match.group(1))
    if batch_match:
        batches[int(batch_match.group(1))] += 1
    required = polyglot_headings if path.is_relative_to(POLYGLOT_PACKAGE) else numbered_headings
    missing = sorted(required - set(text.splitlines()))
    require(not missing, f"missing required sections in {path.relative_to(ROOT)}: {missing}")

require(len(ids) == len(set(ids)), "Project Synthesis PG identifiers must be unique")
require(set(batches) == set(range(46, 81)), f"expected Batch 46-80 coverage, found {sorted(batches)}")
require(ids == [f"PG{index:03d}" for index in range(1, 418)], "PG identifiers must be contiguous PG001-PG417")

installed_entries: list[dict[str, Any]] = []
for batch in range(66, 81):
    batch_manifest_path = POLYGLOT_PACKAGE / "manifests" / f"batch-{batch}.json"
    require(batch_manifest_path.is_file(), f"Batch {batch} source manifest is missing")
    if not batch_manifest_path.is_file():
        continue
    batch_manifest = load_json(batch_manifest_path)
    entries = batch_manifest.get("skills", [])
    require(batch_manifest.get("batch") == batch, f"Batch {batch} source manifest identity is invalid")
    require(len(entries) == batch_manifest.get("skill_count"), f"Batch {batch} source manifest count is invalid")
    installed_entries.extend(entries)

require(len(installed_entries) == 195, f"expected 195 installed Runtime Skill declarations, found {len(installed_entries)}")
for entry in installed_entries:
    name = entry.get("name")
    canonical = POLYGLOT_PACKAGE / str(entry.get("path"))
    installed = RUNTIME_ROOT / str(name) / "SKILL.md"
    interface = installed.parent / "agents" / "openai.yaml"
    require(canonical.is_file(), f"canonical Runtime Skill is missing: {name}")
    require(installed.is_file(), f"installed Runtime Skill is missing: {name}")
    if canonical.is_file() and installed.is_file():
        require(sha256(installed) == sha256(canonical), f"installed Runtime Skill differs from canonical source: {name}")
    require(interface.is_file(), f"installed Runtime Skill interface is missing: {name}")
    if interface.is_file():
        require(f"${name}" in interface.read_text(encoding="utf-8"), f"installed Runtime Skill interface is stale: {name}")

# Batch 81-95 intentionally reuses PG223-PG402 inside the separate
# elmos.language-packs namespace. Preserve that collision and validate the
# deterministic b81-b95 installed aliases instead of relabeling source IDs.
language_file_entries = language_manifest.get("files", [])
require(isinstance(language_file_entries, list) and len(language_file_entries) == 267, "Batch 81-95 package manifest must bind exactly 267 payload files")
language_manifest_paths: set[str] = set()
for entry in language_file_entries if isinstance(language_file_entries, list) else []:
    relative = entry.get("path") if isinstance(entry, dict) else None
    path = LANGUAGE_PACKAGE / relative if isinstance(relative, str) else LANGUAGE_PACKAGE
    require(isinstance(relative, str) and path.is_file(), f"Batch 81-95 manifest file is missing: {relative}")
    if isinstance(relative, str):
        require(relative not in language_manifest_paths, f"Batch 81-95 manifest duplicates {relative}")
        language_manifest_paths.add(relative)
    if isinstance(relative, str) and path.is_file():
        require(path.stat().st_size == entry.get("size_bytes"), f"Batch 81-95 file size mismatch: {relative}")
        require(sha256(path) == entry.get("sha256"), f"Batch 81-95 file digest mismatch: {relative}")

language_sums_path = LANGUAGE_PACKAGE / "SHA256SUMS.txt"
require(language_sums_path.is_file(), "Batch 81-95 SHA256SUMS.txt is missing")
language_sums: dict[str, str] = {}
if language_sums_path.is_file():
    for line_number, line in enumerate(language_sums_path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            errors.append(f"Batch 81-95 invalid SHA256SUMS line {line_number}")
            continue
        relative = parts[1].lstrip("*")
        path = LANGUAGE_PACKAGE / relative
        require(relative not in language_sums, f"Batch 81-95 SHA256SUMS duplicates {relative}")
        language_sums[relative] = parts[0]
        require(path.is_file(), f"Batch 81-95 SHA256SUMS file is missing: {relative}")
        if path.is_file():
            require(sha256(path) == parts[0], f"Batch 81-95 SHA256SUMS digest mismatch: {relative}")
require(len(language_sums) == 268, f"Batch 81-95 SHA256SUMS must bind 268 files, found {len(language_sums)}")
require(set(language_sums) == language_manifest_paths | {"package-manifest.json"}, "Batch 81-95 SHA256SUMS and package manifest inventories disagree")

language_batch_entries: list[dict[str, Any]] = []
for batch in range(81, 96):
    batch_manifest_path = LANGUAGE_PACKAGE / f"batch-{batch}-manifest.json"
    require(batch_manifest_path.is_file(), f"Batch {batch} Language Pack manifest is missing")
    if not batch_manifest_path.is_file():
        continue
    batch_manifest = load_json(batch_manifest_path)
    entries = batch_manifest.get("skills", [])
    require(batch_manifest.get("engine") == "elmos.language-packs", f"Batch {batch} Language Pack engine is invalid")
    require(batch_manifest.get("batch") == batch, f"Batch {batch} Language Pack identity is invalid")
    require(isinstance(entries, list) and len(entries) == 12 and batch_manifest.get("skill_count") == 12, f"Batch {batch} Language Pack count is invalid")
    language_batch_entries.extend(entries if isinstance(entries, list) else [])
require(len(language_batch_entries) == 180, "Batch 81-95 manifests must declare exactly 180 Skills")
require([entry.get("id") for entry in language_batch_entries] == [f"PG{number:03d}" for number in range(223, 403)], "Batch 81-95 source IDs must remain package-local PG223-PG402")
require([entry.get("path") for entry in language_batch_entries] == [path.relative_to(LANGUAGE_PACKAGE).as_posix() for path in language_skills], "Batch 81-95 manifests and Skill paths disagree")
for entry in language_batch_entries:
    relative = entry.get("path")
    path = LANGUAGE_PACKAGE / str(relative)
    require(path.is_file(), f"Batch 81-95 Language Pack Skill is missing: {relative}")
    if not path.is_file():
        continue
    text = path.read_text(encoding="utf-8")
    require(re.search(rf"^id:\s*{re.escape(str(entry.get('id')))}\s*$", text, re.MULTILINE) is not None, f"Batch 81-95 Skill ID mismatch: {relative}")
    require(re.search(rf"^name:\s*{re.escape(str(entry.get('name')))}\s*$", text, re.MULTILINE) is not None, f"Batch 81-95 Skill name mismatch: {relative}")
    require(re.search(r"^status:\s*proposed\s*$", text, re.MULTILINE) is not None, f"Batch 81-95 Skill status must remain proposed: {relative}")
    missing = sorted(numbered_headings - set(text.splitlines()))
    require(not missing, f"Batch 81-95 Skill sections are incomplete: {relative}: {missing}")

require(LANGUAGE_INSTALL_MANIFEST.is_file(), "Batch 81-95 normalized install manifest is missing")
language_install_manifest = load_json(LANGUAGE_INSTALL_MANIFEST) if LANGUAGE_INSTALL_MANIFEST.is_file() else {}
require(language_install_manifest.get("source_id_namespace") == "package-local-language-pack", "Batch 81-95 source namespace is invalid")
require(language_install_manifest.get("source_id_range") == ["PG223", "PG402"], "Batch 81-95 installed manifest relabels source IDs")
require(language_install_manifest.get("skill_count") == 180, "Batch 81-95 installed manifest must contain 180 Skills")
collision = language_install_manifest.get("global_pg_collision", {})
require(collision.get("detected") is True, "Batch 81-95 global PG collision must remain explicit")
language_installed_entries = language_install_manifest.get("skills", [])
require(isinstance(language_installed_entries, list) and len(language_installed_entries) == 180, "Batch 81-95 normalized Skill inventory is invalid")
for source_entry, installed_entry in zip(language_batch_entries, language_installed_entries):
    alias = f"b{source_entry.get('batch')}-{source_entry.get('name')}"
    source_key = f"LP-B{source_entry.get('batch')}-{source_entry.get('id')}"
    require(installed_entry.get("source_key") == source_key, f"Batch 81-95 source key mismatch: {source_key}")
    require(installed_entry.get("source_id") == source_entry.get("id"), f"Batch 81-95 source ID binding mismatch: {source_key}")
    require(installed_entry.get("source_name") == source_entry.get("name"), f"Batch 81-95 source name binding mismatch: {source_key}")
    require(installed_entry.get("installed_name") == alias, f"Batch 81-95 normalized name mismatch: {source_key}")
    canonical = LANGUAGE_PACKAGE / str(source_entry.get("path"))
    require(installed_entry.get("source_sha256") == "sha256:" + sha256(canonical), f"Batch 81-95 canonical digest mismatch: {source_key}")
    installed = ROOT / str(installed_entry.get("installed_path"))
    interface = ROOT / str(installed_entry.get("interface_path"))
    require(installed.is_file(), f"Batch 81-95 normalized Runtime Skill is missing: {alias}")
    require(interface.is_file(), f"Batch 81-95 normalized Runtime Skill interface is missing: {alias}")
    if installed.is_file():
        require(installed_entry.get("installed_sha256") == "sha256:" + sha256(installed), f"Batch 81-95 normalized Runtime Skill digest mismatch: {alias}")
        installed_text = installed.read_text(encoding="utf-8")
        require(re.search(rf"^name:\s*{re.escape(alias)}\s*$", installed_text, re.MULTILINE) is not None, f"Batch 81-95 normalized frontmatter name mismatch: {alias}")
        require(f'source_id: "{source_entry.get("id")}"' in installed_text, f"Batch 81-95 normalized source ID metadata is missing: {alias}")
    if interface.is_file():
        require(installed_entry.get("interface_sha256") == "sha256:" + sha256(interface), f"Batch 81-95 Runtime Skill interface digest mismatch: {alias}")
        require(f"${alias}" in interface.read_text(encoding="utf-8"), f"Batch 81-95 Runtime Skill interface is stale: {alias}")

for schema in schemas:
    try:
        load_json(schema)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid Project Synthesis schema {schema.relative_to(ROOT)}: {exc}")

runtime_files = [
    ROOT / ".agents/skills/elmos-project-synthesis/SKILL.md",
    ROOT / ".agents/skills/elmos-project-synthesis/agents/openai.yaml",
    ROOT / ".agents/skills/elmos-project-synthesis/scripts/synthesize.py",
    ROOT / "contracts/project-synthesis-schema/synthesis-request-v1.schema.json",
    ROOT / "engines/project-synthesis-engine/pyproject.toml",
    ROOT / "engines/project-synthesis-engine/uv.lock",
    ROOT / "engines/project-synthesis-engine/scripts/run_acceptance.py",
]
for path in runtime_files:
    require(path.is_file(), f"required integration file is missing: {path.relative_to(ROOT)}")

if errors:
    print("\n".join(f"ERROR: {error}" for error in errors), file=sys.stderr)
    raise SystemExit(1)
print(
    f"OK: {len(skills)} global Project Synthesis skills + {len(language_skills)} "
    f"package-local Language Pack skills, {len(schemas) + 1} schemas, Batch 46-95 runtime integration"
)
