#!/usr/bin/env python3
"""Import Batch 81-95 Language Packs without colliding with global PG IDs."""

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
PACKAGE_NAME = "elmos-language-packs-batch81-95-complete"
PACKAGE_ROOT = ROOT / PACKAGE_NAME
RUNTIME_ROOT = ROOT / "agent-skills" / "runtime"
INSTALL_MANIFEST = ROOT / "docs" / "language-packs-batch81-95" / "installed-manifest.json"
SKILL_GENERATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/generate_openai_yaml.py"
)
EXPECTED_SKILLS = 180
EXPECTED_SOURCE_IDS = [f"PG{number:03d}" for number in range(223, 403)]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_generator() -> ModuleType:
    if not SKILL_GENERATOR.is_file():
        raise SystemExit(f"Skill interface generator is missing: {SKILL_GENERATOR}")
    spec = importlib.util.spec_from_file_location("elmos_skill_interface_generator", SKILL_GENERATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load Skill interface generator: {SKILL_GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_sha256s(source: Path) -> dict[str, str]:
    sums_path = source / "SHA256SUMS.txt"
    if not sums_path.is_file():
        raise SystemExit(f"SHA256SUMS.txt is missing: {sums_path}")
    entries: dict[str, str] = {}
    for line_number, line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise SystemExit(f"Invalid SHA256SUMS.txt line {line_number}")
        relative = parts[1].strip().lstrip("*")
        if not relative or relative in entries:
            raise SystemExit(f"Duplicate or empty SHA256SUMS path on line {line_number}")
        path = (source / relative).resolve()
        try:
            path.relative_to(source.resolve())
        except ValueError as exc:
            raise SystemExit(f"SHA256SUMS path escapes package: {relative}") from exc
        if not path.is_file() or sha256_file(path) != parts[0]:
            raise SystemExit(f"SHA256SUMS mismatch: {relative}")
        entries[relative] = parts[0]
    if len(entries) != 268:
        raise SystemExit(f"Expected 268 SHA256SUMS entries, found {len(entries)}")
    return entries


def source_files(source: Path) -> list[str]:
    return sorted(
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )


def validate_source(source: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, str]]:
    package_manifest_path = source / "package-manifest.json"
    if not package_manifest_path.is_file():
        raise SystemExit(f"Package manifest is missing: {package_manifest_path}")
    manifest = load_json(package_manifest_path)
    if manifest.get("package") != PACKAGE_NAME:
        raise SystemExit("Language Pack package identity is invalid")
    if manifest.get("skills") != EXPECTED_SKILLS:
        raise SystemExit("Language Pack package must declare exactly 180 Skills")
    if manifest.get("batches") != list(range(81, 96)):
        raise SystemExit("Language Pack batches must be exactly 81-95")
    if manifest.get("skill_id_range") != ["PG223", "PG402"]:
        raise SystemExit("Language Pack source ID range must be PG223-PG402")

    sums = parse_sha256s(source)
    listed = manifest.get("files")
    if not isinstance(listed, list) or len(listed) != 267:
        raise SystemExit("Package manifest must contain exactly 267 files")
    for entry in listed:
        if not isinstance(entry, dict):
            raise SystemExit("Package manifest file entry must be an object")
        relative = entry.get("path")
        if not isinstance(relative, str) or sums.get(relative) != entry.get("sha256"):
            raise SystemExit(f"Package manifest/SHA256SUMS mismatch: {relative}")
        path = source / relative
        if path.stat().st_size != entry.get("size_bytes"):
            raise SystemExit(f"Package manifest file size mismatch: {relative}")
    actual = set(source_files(source))
    expected_actual = set(sums) | {"SHA256SUMS.txt", "VALIDATION_REPORT.json"}
    if actual != expected_actual:
        raise SystemExit(
            f"Unexpected source package files: missing={sorted(expected_actual - actual)}, "
            f"extra={sorted(actual - expected_actual)}"
        )
    validation_report = load_json(source / "VALIDATION_REPORT.json")
    if (
        validation_report.get("status") != "PASSED"
        or validation_report.get("skill_count") != EXPECTED_SKILLS
        or validation_report.get("batch_count") != 15
    ):
        raise SystemExit("Source validation report is invalid")

    skills: list[dict[str, Any]] = []
    for batch in range(81, 96):
        batch_manifest = load_json(source / f"batch-{batch}-manifest.json")
        entries = batch_manifest.get("skills")
        if (
            batch_manifest.get("engine") != "elmos.language-packs"
            or batch_manifest.get("batch") != batch
            or not isinstance(entries, list)
            or len(entries) != 12
            or batch_manifest.get("skill_count") != 12
        ):
            raise SystemExit(f"Batch {batch} manifest is invalid")
        skills.extend(entries)
    source_ids = [skill.get("id") for skill in skills]
    source_names = [skill.get("name") for skill in skills]
    aliases = [installed_name(skill) for skill in skills]
    if source_ids != EXPECTED_SOURCE_IDS:
        raise SystemExit("Language Pack source IDs must be contiguous package-local PG223-PG402")
    if len(set(source_names)) != EXPECTED_SKILLS or len(set(aliases)) != EXPECTED_SKILLS:
        raise SystemExit("Language Pack source or installed names are duplicated")
    if any(len(alias) > 64 for alias in aliases):
        raise SystemExit("Normalized Language Pack Skill name exceeds 64 characters")
    return manifest, skills, sums


def installed_name(skill: dict[str, Any]) -> str:
    return f"b{skill['batch']}-{skill['name']}"


def copy_exact(source: Path, destination: Path) -> None:
    if destination.exists():
        if destination.is_file() and sha256_file(destination) == sha256_file(source):
            return
        raise SystemExit(f"Refusing to overwrite different destination: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def normalized_skill(source: Path, skill: dict[str, Any], source_digest: str) -> str:
    text = source.read_text(encoding="utf-8")
    match = re.match(r"^---\n.*?\n---\n?", text, re.DOTALL)
    if match is None:
        raise SystemExit(f"Source Skill frontmatter is invalid: {source}")
    alias = installed_name(skill)
    description = (
        f"Use when ELMOS must run {skill['name'].replace('-', ' ')} for Batch {skill['batch']} "
        f"{skill['batch_title']}. Preserve native semantics, safety boundaries, ownership, "
        "traceability, and fail-closed evidence; require real vendor toolchain execution for runtime claims."
    )
    body = text[match.end() :].lstrip("\n")
    body = re.sub(
        rf"^# {re.escape(skill['id'])} — ",
        f"# Batch {skill['batch']} Language Pack / source {skill['id']} — ",
        body,
        count=1,
        flags=re.MULTILINE,
    )
    frontmatter = "\n".join(
        [
            "---",
            f"name: {alias}",
            f"description: {json.dumps(description, ensure_ascii=False)}",
            "metadata:",
            f"  source_package: {json.dumps(PACKAGE_NAME)}",
            f"  source_id: {json.dumps(skill['id'])}",
            f"  source_name: {json.dumps(skill['name'])}",
            f"  source_sha256: {json.dumps('sha256:' + source_digest)}",
            f"  batch: {skill['batch']}",
            '  source_engine: "elmos.language-packs"',
            '  source_status: "proposed"',
            '  normalized_namespace: "language-pack"',
            "---",
            "",
        ]
    )
    return frontmatter + body


def expected_interface(name: str, generator: ModuleType) -> str:
    display = generator.format_display_name(name)
    short = "Run this ELMOS language-pack Skill with evidence"
    prompt = f"Use ${name} to execute this ELMOS Language Pack Skill with fail-closed evidence."
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
            "short_description=Run this ELMOS language-pack Skill with evidence",
            f"default_prompt=Use ${name} to execute this ELMOS Language Pack Skill with fail-closed evidence.",
        ],
    )
    if result is None or interface.read_text(encoding="utf-8") != expected:
        raise SystemExit(f"Skill interface generation failed: {name}")


def expected_install_manifest(
    source: Path,
    skills: list[dict[str, Any]],
    sums: dict[str, str],
) -> dict[str, Any]:
    installed: list[dict[str, Any]] = []
    for skill in skills:
        alias = installed_name(skill)
        installed_skill = RUNTIME_ROOT / alias / "SKILL.md"
        interface = installed_skill.parent / "agents" / "openai.yaml"
        installed.append(
            {
                "batch": skill["batch"],
                "source_id": skill["id"],
                "source_key": f"LP-B{skill['batch']}-{skill['id']}",
                "source_name": skill["name"],
                "source_path": skill["path"],
                "source_sha256": "sha256:" + sums[skill["path"]],
                "installed_name": alias,
                "installed_path": installed_skill.relative_to(ROOT).as_posix(),
                "installed_sha256": "sha256:" + sha256_file(installed_skill),
                "interface_path": interface.relative_to(ROOT).as_posix(),
                "interface_sha256": "sha256:" + sha256_file(interface),
            }
        )
    return {
        "schema_version": "1.0",
        "package": PACKAGE_NAME,
        "source_engine": "elmos.language-packs",
        "source_id_namespace": "package-local-language-pack",
        "source_id_range": ["PG223", "PG402"],
        "global_pg_collision": {
            "detected": True,
            "conflicts_with": "elmos-codex-skills-batch66-80-complete PG223-PG417",
            "resolution": "Preserve source IDs and install deterministic b81-b95 aliases; do not append to the global PG sequence.",
        },
        "batches": list(range(81, 96)),
        "source_file_count": len(source_files(source)),
        "source_package_manifest_sha256": "sha256:" + sha256_file(source / "package-manifest.json"),
        "source_sha256s_sha256": "sha256:" + sha256_file(source / "SHA256SUMS.txt"),
        "source_validation_report_sha256": "sha256:" + sha256_file(source / "VALIDATION_REPORT.json"),
        "skill_count": len(installed),
        "skills": installed,
    }


def verify_destination(
    manifest: dict[str, Any],
    skills: list[dict[str, Any]],
    sums: dict[str, str],
    generator: ModuleType,
) -> None:
    destination_manifest, destination_skills, destination_sums = validate_source(PACKAGE_ROOT)
    if destination_manifest != manifest or destination_sums != sums:
        raise SystemExit("Imported Language Pack source differs from validated source")
    if [skill["id"] for skill in destination_skills] != [skill["id"] for skill in skills]:
        raise SystemExit("Imported Language Pack Skill inventory differs from source")
    for skill in skills:
        alias = installed_name(skill)
        installed = RUNTIME_ROOT / alias / "SKILL.md"
        canonical = PACKAGE_ROOT / skill["path"]
        expected = normalized_skill(canonical, skill, sums[skill["path"]])
        if not installed.is_file() or installed.read_text(encoding="utf-8") != expected:
            raise SystemExit(f"Installed normalized Language Pack Skill is missing or changed: {alias}")
        interface = installed.parent / "agents" / "openai.yaml"
        if not interface.is_file() or interface.read_text(encoding="utf-8") != expected_interface(
            alias, generator
        ):
            raise SystemExit(f"Installed Language Pack Skill interface is missing or changed: {alias}")
    expected_manifest = expected_install_manifest(PACKAGE_ROOT, skills, sums)
    if not INSTALL_MANIFEST.is_file() or load_json(INSTALL_MANIFEST) != expected_manifest:
        raise SystemExit("Installed Language Pack manifest is missing or stale")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = (
        args.source
        if args.source is not None
        else PACKAGE_ROOT if args.check else Path("/Users/stephen/Downloads") / PACKAGE_NAME
    ).resolve()
    manifest, skills, sums = validate_source(source)
    generator = load_generator()

    if not args.check:
        for relative in source_files(source):
            copy_exact(source / relative, PACKAGE_ROOT / relative)
        for skill in skills:
            alias = installed_name(skill)
            canonical = PACKAGE_ROOT / skill["path"]
            installed = RUNTIME_ROOT / alias / "SKILL.md"
            expected = normalized_skill(canonical, skill, sums[skill["path"]])
            if installed.exists():
                if not installed.is_file() or installed.read_text(encoding="utf-8") != expected:
                    raise SystemExit(f"Refusing to overwrite different Runtime Skill: {installed}")
            else:
                installed.parent.mkdir(parents=True, exist_ok=True)
                installed.write_text(expected, encoding="utf-8")
            install_interface(installed.parent, alias, generator)
        expected_manifest = expected_install_manifest(PACKAGE_ROOT, skills, sums)
        rendered = json.dumps(expected_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if INSTALL_MANIFEST.exists():
            if INSTALL_MANIFEST.read_text(encoding="utf-8") != rendered:
                raise SystemExit(f"Refusing to overwrite different install manifest: {INSTALL_MANIFEST}")
        else:
            INSTALL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            INSTALL_MANIFEST.write_text(rendered, encoding="utf-8")

    verify_destination(manifest, skills, sums, generator)
    print(
        json.dumps(
            {
                "package": PACKAGE_NAME,
                "batches": [81, 95],
                "source_id_range": ["PG223", "PG402"],
                "source_namespace": "package-local-language-pack",
                "skills": len(skills),
                "interfaces": len(skills),
                "status": "verified" if args.check else "imported-and-verified",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
