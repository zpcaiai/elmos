#!/usr/bin/env python3
"""Import and verify the immutable Batch 66-80 Skill distribution."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "elmos-codex-skills-batch66-80-complete"
PACKAGE_ROOT = ROOT / PACKAGE_NAME
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
SKILL_GENERATOR = (
    Path("/Users/stephen/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py")
)
EXPECTED_SKILLS = 195
EXPECTED_IDS = [f"PG{number:03d}" for number in range(223, 418)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_generator() -> ModuleType:
    if not SKILL_GENERATOR.is_file():
        raise SystemExit(f"Skill interface generator is missing: {SKILL_GENERATOR}")
    spec = importlib.util.spec_from_file_location("elmos_skill_interface_generator", SKILL_GENERATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load Skill interface generator: {SKILL_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_source(source: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest_path = source / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Source manifest is missing: {manifest_path}")
    manifest = load_json(manifest_path)
    if manifest.get("package") != PACKAGE_NAME:
        raise SystemExit("Source package identity is invalid")
    if manifest.get("skill_count") != EXPECTED_SKILLS:
        raise SystemExit("Source package must declare exactly 195 Skills")
    if manifest.get("id_range") != ["PG223", "PG417"]:
        raise SystemExit("Source package ID range must be PG223-PG417")
    if manifest.get("batches") != list(range(66, 81)):
        raise SystemExit("Source package batches must be exactly 66-80")

    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("Source package manifest has no file inventory")
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise SystemExit("Source package file inventory contains a non-object")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative or relative in seen:
            raise SystemExit(f"Invalid or duplicate source file path: {relative!r}")
        seen.add(relative)
        path = (source / relative).resolve()
        try:
            path.relative_to(source.resolve())
        except ValueError as exc:
            raise SystemExit(f"Source file escapes package: {relative}") from exc
        if not path.is_file():
            raise SystemExit(f"Source file is missing: {relative}")
        if path.stat().st_size != entry.get("size_bytes"):
            raise SystemExit(f"Source file size mismatch: {relative}")
        if sha256_file(path) != entry.get("sha256"):
            raise SystemExit(f"Source file digest mismatch: {relative}")

    skills: list[dict[str, Any]] = []
    for batch in range(66, 81):
        batch_manifest = load_json(source / "manifests" / f"batch-{batch}.json")
        if batch_manifest.get("batch") != batch:
            raise SystemExit(f"Batch {batch} manifest identity is invalid")
        entries = batch_manifest.get("skills")
        if not isinstance(entries, list) or len(entries) != batch_manifest.get("skill_count"):
            raise SystemExit(f"Batch {batch} manifest skill count is invalid")
        skills.extend(entries)
    ids = [skill.get("id") for skill in skills]
    names = [skill.get("name") for skill in skills]
    if ids != EXPECTED_IDS:
        raise SystemExit("Source Skill IDs are not contiguous PG223-PG417")
    if len(names) != EXPECTED_SKILLS or len(set(names)) != EXPECTED_SKILLS:
        raise SystemExit("Source Skill names are missing or duplicated")
    if any(not isinstance(name, str) or len(name) > 64 for name in names):
        raise SystemExit("Source Skill name is invalid or longer than 64 characters")
    return manifest, skills


def copy_exact(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == sha256_file(source):
            return
        raise SystemExit(f"Refusing to overwrite different destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def expected_interface(name: str, generator: ModuleType) -> str:
    display = generator.format_display_name(name)
    short = "Run this ELMOS project Skill with evidence controls"
    prompt = f"Use ${name} to execute this ELMOS project Skill with fail-closed evidence."
    return "\n".join(
        [
            "interface:",
            f"  display_name: {generator.yaml_quote(display)}",
            f"  short_description: {generator.yaml_quote(short)}",
            f"  default_prompt: {generator.yaml_quote(prompt)}",
            "",
        ]
    )


def install_interface(skill_dir: Path, name: str, generator: ModuleType) -> None:
    interface = skill_dir / "agents" / "openai.yaml"
    expected = expected_interface(name, generator)
    if interface.exists():
        if interface.is_file() and interface.read_text(encoding="utf-8") == expected:
            return
        raise SystemExit(f"Refusing to overwrite different Skill interface: {interface}")
    result = generator.write_openai_yaml(
        skill_dir,
        name,
        [
            "short_description=Run this ELMOS project Skill with evidence controls",
            f"default_prompt=Use ${name} to execute this ELMOS project Skill with fail-closed evidence.",
        ],
    )
    if result is None or interface.read_text(encoding="utf-8") != expected:
        raise SystemExit(f"Skill interface generation failed: {name}")


def verify_destination(manifest: dict[str, Any], skills: list[dict[str, Any]], generator: ModuleType) -> None:
    destination_manifest = PACKAGE_ROOT / "manifest.json"
    if not destination_manifest.is_file() or load_json(destination_manifest) != manifest:
        raise SystemExit("Imported package manifest is missing or changed")
    for entry in manifest["files"]:
        path = PACKAGE_ROOT / entry["path"]
        if (
            not path.is_file()
            or path.stat().st_size != entry["size_bytes"]
            or sha256_file(path) != entry["sha256"]
        ):
            raise SystemExit(f"Imported package file is missing or changed: {entry['path']}")

    for skill in skills:
        name = skill["name"]
        canonical = PACKAGE_ROOT / skill["path"]
        installed = RUNTIME_ROOT / name / "SKILL.md"
        if not installed.is_file() or sha256_file(installed) != sha256_file(canonical):
            raise SystemExit(f"Installed Runtime Skill is missing or changed: {name}")
        text = installed.read_text(encoding="utf-8")
        if not re.search(rf"^name:\s*{re.escape(name)}\s*$", text, re.MULTILINE):
            raise SystemExit(f"Installed Runtime Skill frontmatter/path mismatch: {name}")
        interface = installed.parent / "agents" / "openai.yaml"
        if not interface.is_file() or interface.read_text(encoding="utf-8") != expected_interface(
            name, generator
        ):
            raise SystemExit(f"Installed Runtime Skill interface is missing or changed: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="Source Batch 66-80 distribution",
    )
    parser.add_argument("--check", action="store_true", help="verify the imported package only")
    args = parser.parse_args()
    source = (
        args.source
        if args.source is not None
        else PACKAGE_ROOT if args.check else Path("/Users/stephen/Downloads") / PACKAGE_NAME
    ).resolve()
    manifest, skills = validate_source(source)
    generator = load_generator()

    if not args.check:
        copy_exact(source / "manifest.json", PACKAGE_ROOT / "manifest.json")
        for entry in manifest["files"]:
            copy_exact(source / entry["path"], PACKAGE_ROOT / entry["path"])
        for skill in skills:
            name = skill["name"]
            canonical = PACKAGE_ROOT / skill["path"]
            installed = RUNTIME_ROOT / name / "SKILL.md"
            copy_exact(canonical, installed)
            install_interface(installed.parent, name, generator)

    verify_destination(manifest, skills, generator)
    print(
        json.dumps(
            {
                "package": PACKAGE_NAME,
                "skills": len(skills),
                "id_range": [skills[0]["id"], skills[-1]["id"]],
                "batches": [66, 80],
                "interfaces": len(skills),
                "status": "verified" if args.check else "imported-and-verified",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
