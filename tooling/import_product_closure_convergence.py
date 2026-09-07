#!/usr/bin/env python3
"""Install and verify the Batch 56A and product-convergence Skill overlays."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

import skill_creator_tools


ROOT = Path(__file__).resolve().parents[1]
BATCH56_PACKAGE = ROOT / "elmos-codex-skills-batch56a-product-closure"
CONVERGENCE_PACKAGE = ROOT / "elmos-product-convergence-reference-skills"
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
AGENT_SKILL_ROOT = ROOT / ".agents" / "skills"
INSTALL_MANIFEST = ROOT / "docs" / "product-closure-convergence" / "installed-manifest.json"
EXPECTED_BATCH56_IDS = [f"CLO56A{number:03d}" for number in range(1, 17)]
EXPECTED_CONVERGENCE_IDS = [f"CONV-{number:03d}" for number in range(1, 33)]
CACHE_PARTS = {"__pycache__", ".DS_Store"}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not CACHE_PARTS.intersection(path.parts)
        and path.suffix != ".pyc"
    )


def safe_relative(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        fail(f"path escapes package root: {relative}")
        raise AssertionError from exc
    return path


def load_skill_tools() -> tuple[ModuleType, Any]:
    return skill_creator_tools, skill_creator_tools.validate_skill


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", text, re.DOTALL)
    if match is None:
        fail(f"invalid Skill frontmatter: {path}")
    payload = yaml.safe_load(match.group(1))
    if not isinstance(payload, dict):
        fail(f"Skill frontmatter must be an object: {path}")
    return payload, text[match.end() :].lstrip("\n")


def expected_interface(name: str, generator: ModuleType, family: str) -> str:
    display = generator.format_display_name(name)
    short = f"Run this ELMOS {family} Skill with evidence"
    prompt = f"Use ${name} to execute this ELMOS {family} Skill with fail-closed evidence."
    return "\n".join(
        [
            "interface:",
            f"  display_name: {generator.yaml_quote(display)}",
            f"  short_description: {generator.yaml_quote(short)}",
            f"  default_prompt: {generator.yaml_quote(prompt)}",
            "",
        ]
    )


def write_exact(path: Path, data: bytes) -> None:
    if path.exists():
        if path.is_file() and path.read_bytes() == data:
            return
        fail(f"refusing to overwrite different file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def copy_exact(source: Path, destination: Path) -> None:
    write_exact(destination, source.read_bytes())


def write_json_exact(path: Path, value: Any) -> None:
    write_exact(path, (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode())


def install_interface(skill_dir: Path, name: str, generator: ModuleType, family: str) -> None:
    expected = expected_interface(name, generator, family)
    write_exact(skill_dir / "agents" / "openai.yaml", expected.encode())


def validate_batch56_source() -> list[dict[str, Any]]:
    manifest = load_json(BATCH56_PACKAGE / "manifest.json")
    skills = manifest.get("skills")
    if (
        manifest.get("schemaVersion") != "1.0"
        or manifest.get("package") != BATCH56_PACKAGE.name
        or manifest.get("batch") != "56A"
        or manifest.get("skillCount") != 16
        or not isinstance(skills, list)
        or len(skills) != 16
    ):
        fail("Batch 56A package identity or Skill count is invalid")
    if [entry.get("id") for entry in skills] != EXPECTED_BATCH56_IDS:
        fail("Batch 56A IDs must be exactly CLO56A001-CLO56A016")
    names: set[str] = set()
    for entry in skills:
        name = entry.get("name")
        relative = entry.get("path")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9-]+", name)
            or len(name) > 64
            or name in names
            or entry.get("batch") != "56A"
            or entry.get("maturity") != "reviewed-design"
            or not isinstance(relative, str)
        ):
            fail(f"invalid Batch 56A Skill entry: {entry}")
        source = safe_relative(BATCH56_PACKAGE, relative)
        if not source.is_file():
            fail(f"missing Batch 56A Skill: {relative}")
        frontmatter, _ = parse_frontmatter(source)
        if frontmatter.get("name") != name or frontmatter.get("id") != entry["id"]:
            fail(f"Batch 56A Skill identity mismatch: {name}")
        names.add(name)
    if len(list((BATCH56_PACKAGE / "schemas").glob("*.json"))) != 3:
        fail("Batch 56A must preserve exactly three Schemas")
    if len(list((BATCH56_PACKAGE / "templates").glob("*.json"))) != 2:
        fail("Batch 56A must preserve exactly two templates")
    return skills


def parse_checksums() -> dict[str, str]:
    checksums: dict[str, str] = {}
    path = CONVERGENCE_PACKAGE / "CHECKSUMS.sha256"
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]) or parts[1] in checksums:
            fail(f"invalid convergence checksum line {number}")
        checksums[parts[1]] = parts[0]
    actual = {
        path.relative_to(CONVERGENCE_PACKAGE).as_posix()
        for path in source_files(CONVERGENCE_PACKAGE)
        if path.name not in {"CHECKSUMS.sha256", "FILE_MANIFEST.txt"}
    }
    if actual != set(checksums):
        fail(f"convergence checksum inventory drift: missing={sorted(set(checksums)-actual)}, extra={sorted(actual-set(checksums))}")
    for relative, digest in checksums.items():
        if sha256_file(CONVERGENCE_PACKAGE / relative) != digest:
            fail(f"convergence checksum mismatch: {relative}")
    inventory = CONVERGENCE_PACKAGE / "FILE_MANIFEST.txt"
    if inventory.read_text(encoding="utf-8").splitlines() != sorted(checksums):
        fail("convergence FILE_MANIFEST.txt must exactly enumerate the checksum inventory")
    return checksums


def validate_convergence_source(validate_skill: Any) -> list[dict[str, Any]]:
    manifest = load_json(CONVERGENCE_PACKAGE / "manifest.json")
    if manifest.get("bundle") != CONVERGENCE_PACKAGE.name or manifest.get("skill_count") != 32 or manifest.get("schema_count") != 12:
        fail("product-convergence bundle identity or counts are invalid")
    parse_checksums()
    registry = load_json(CONVERGENCE_PACKAGE / "product-convergence" / "skill-registry.json")
    skills = registry.get("skills")
    if not isinstance(skills, list) or len(skills) != 32:
        fail("product-convergence registry must contain exactly 32 Skills")
    if [entry.get("skill_id") for entry in skills] != EXPECTED_CONVERGENCE_IDS:
        fail("product-convergence IDs must be exactly CONV-001-CONV-032")
    names: set[str] = set()
    for entry in skills:
        name = entry.get("name")
        if not isinstance(name, str) or name in names or not name.startswith("conv-") or len(name) > 64:
            fail(f"invalid convergence Skill name: {name}")
        source = CONVERGENCE_PACKAGE / ".agents" / "skills" / name / "SKILL.md"
        if entry.get("path") != f".agents/skills/{name}/SKILL.md" or not source.is_file():
            fail(f"convergence Skill path mismatch: {name}")
        valid, message = validate_skill(source.parent)
        if not valid:
            fail(f"skill-creator-compatible convergence validation failed for {name}: {message}")
        names.add(name)
    return skills


def normalized_batch56_skill(entry: dict[str, Any]) -> bytes:
    source = BATCH56_PACKAGE / entry["path"]
    frontmatter, body = parse_frontmatter(source)
    normalized = {
        "name": entry["name"],
        "description": frontmatter["description"],
        "metadata": {
            "source_package": BATCH56_PACKAGE.name,
            "source_id": entry["id"],
            "source_batch": "56A",
            "source_maturity": "reviewed-design",
            "source_sha256": "sha256:" + sha256_file(source),
            "normalized_namespace": "product-closure",
        },
    }
    rendered = "---\n" + yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False).strip() + "\n---\n\n" + body
    return rendered.encode()


def integrated_asset_pairs() -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for directory in ("schemas", "templates"):
        for source in source_files(BATCH56_PACKAGE / directory):
            pairs.append((source, ROOT / directory / "product-closure-batch56a" / source.name))
    for directory in ("docs", "references"):
        for source in source_files(BATCH56_PACKAGE / directory):
            pairs.append((source, ROOT / "docs" / "product-closure-batch56a" / directory / source.name))
    for directory in ("schemas", "templates", "scripts", "tests", "docs", "product-convergence"):
        source_root = CONVERGENCE_PACKAGE / directory
        for source in source_files(source_root):
            pairs.append((source, ROOT / source.relative_to(CONVERGENCE_PACKAGE)))
    return pairs


def expected_manifest(
    batch56_skills: list[dict[str, Any]],
    convergence_skills: list[dict[str, Any]],
) -> dict[str, Any]:
    batch56_records = []
    for entry in batch56_skills:
        source = BATCH56_PACKAGE / entry["path"]
        target = RUNTIME_ROOT / entry["name"] / "SKILL.md"
        interface = target.parent / "agents" / "openai.yaml"
        batch56_records.append(
            {
                "id": entry["id"],
                "name": entry["name"],
                "maturity": "reviewed-design",
                "source_path": source.relative_to(ROOT).as_posix(),
                "source_sha256": "sha256:" + sha256_file(source),
                "installed_path": target.relative_to(ROOT).as_posix(),
                "installed_sha256": "sha256:" + sha256_file(target),
                "interface_sha256": "sha256:" + sha256_file(interface),
            }
        )
    convergence_records = []
    for entry in convergence_skills:
        source = CONVERGENCE_PACKAGE / entry["path"]
        target = AGENT_SKILL_ROOT / entry["name"] / "SKILL.md"
        interface = target.parent / "agents" / "openai.yaml"
        convergence_records.append(
            {
                "id": entry["skill_id"],
                "name": entry["name"],
                "layer": entry["layer"],
                "source_path": source.relative_to(ROOT).as_posix(),
                "source_sha256": "sha256:" + sha256_file(source),
                "installed_path": target.relative_to(ROOT).as_posix(),
                "installed_sha256": "sha256:" + sha256_file(target),
                "interface_sha256": "sha256:" + sha256_file(interface),
            }
        )
    assets = [
        {
            "source_path": source.relative_to(ROOT).as_posix(),
            "installed_path": target.relative_to(ROOT).as_posix(),
            "sha256": "sha256:" + sha256_file(target),
        }
        for source, target in integrated_asset_pairs()
    ]
    return {
        "schema_version": "1.0",
        "namespace_policy": {
            "batch56a": "Product closure reviewed-design overlay; not Migration M56",
            "convergence": "Repository implementation overlay; does not add a feature Batch",
        },
        "batch56a": {
            "package": BATCH56_PACKAGE.name,
            "skills": batch56_records,
            "skill_count": 16,
            "external_evidence": "NOT_RUN",
            "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        },
        "convergence": {
            "package": CONVERGENCE_PACKAGE.name,
            "skills": convergence_records,
            "skill_count": 32,
            "external_evidence": "NOT_RUN",
            "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        },
        "integrated_assets": assets,
    }


def install() -> None:
    generator, validate_skill = load_skill_tools()
    batch56_skills = validate_batch56_source()
    convergence_skills = validate_convergence_source(validate_skill)
    for entry in batch56_skills:
        target = RUNTIME_ROOT / entry["name"]
        write_exact(target / "SKILL.md", normalized_batch56_skill(entry))
        install_interface(target, entry["name"], generator, "product-closure")
    for entry in convergence_skills:
        source = CONVERGENCE_PACKAGE / entry["path"]
        target = AGENT_SKILL_ROOT / entry["name"]
        copy_exact(source, target / "SKILL.md")
        install_interface(target, entry["name"], generator, "product-convergence")
    for source, target in integrated_asset_pairs():
        copy_exact(source, target)
    write_json_exact(INSTALL_MANIFEST, expected_manifest(batch56_skills, convergence_skills))
    verify()


def verify() -> None:
    generator, validate_skill = load_skill_tools()
    batch56_skills = validate_batch56_source()
    convergence_skills = validate_convergence_source(validate_skill)
    for entry in batch56_skills:
        target = RUNTIME_ROOT / entry["name"]
        if not (target / "SKILL.md").is_file() or (target / "SKILL.md").read_bytes() != normalized_batch56_skill(entry):
            fail(f"Batch 56A installed Skill is missing or changed: {entry['name']}")
        valid, message = validate_skill(target)
        if not valid:
            fail(f"skill-creator-compatible installed Batch 56A validation failed for {entry['name']}: {message}")
        if (target / "agents" / "openai.yaml").read_text(encoding="utf-8") != expected_interface(entry["name"], generator, "product-closure"):
            fail(f"Batch 56A interface is missing or changed: {entry['name']}")
    for entry in convergence_skills:
        target = AGENT_SKILL_ROOT / entry["name"]
        source = CONVERGENCE_PACKAGE / entry["path"]
        if not (target / "SKILL.md").is_file() or sha256_file(target / "SKILL.md") != sha256_file(source):
            fail(f"convergence installed Skill is missing or changed: {entry['name']}")
        valid, message = validate_skill(target)
        if not valid:
            fail(f"skill-creator-compatible installed convergence validation failed for {entry['name']}: {message}")
        if (target / "agents" / "openai.yaml").read_text(encoding="utf-8") != expected_interface(entry["name"], generator, "product-convergence"):
            fail(f"convergence interface is missing or changed: {entry['name']}")
    for source, target in integrated_asset_pairs():
        if not target.is_file() or sha256_file(source) != sha256_file(target):
            fail(f"integrated product-closure asset is missing or changed: {target}")
    if not INSTALL_MANIFEST.is_file():
        fail("product-closure installed manifest is missing")
    expected = expected_manifest(batch56_skills, convergence_skills)
    if load_json(INSTALL_MANIFEST) != expected:
        fail("product-closure installed manifest is stale")
    print(
        json.dumps(
            {
                "status": "PASS",
                "batch56a_runtime_skills": 16,
                "convergence_agent_skills": 32,
                "skill_creator_compatible_validation": 48,
                "interfaces": 48,
                "integrated_assets": len(integrated_asset_pairs()),
                "external_evidence": "NOT_RUN",
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if args.install:
        install()
    else:
        verify()


if __name__ == "__main__":
    main()
