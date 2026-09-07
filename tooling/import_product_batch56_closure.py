#!/usr/bin/env python3
"""Import and verify the Product Batch 56 reviewed-guidance Skill package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import skill_creator_tools
import yaml

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "elmos-codex-skills-batch56-product-closure"
RUNTIME = ROOT / "agent-skills" / "runtime"
DOC_ROOT = ROOT / "docs" / "product-closure-batch56"
INSTALLED_MANIFEST = DOC_ROOT / "installed-manifest.json"
SOURCE_INVENTORY = DOC_ROOT / "source-inventory.json"
OVERLAP_MAP = DOC_ROOT / "overlap-map.json"
EXPECTED_IDS = [f"C56-{number:02d}" for number in range(1, 17)]
EXPECTED_SOURCE_FILE_COUNT = 25
INVALID_SOURCE_NAME_IDS = {"C56-09", "C56-10", "C56-13", "C56-15", "C56-16"}
IGNORED_PARTS = {"__pycache__", ".DS_Store"}
OVERLAP_TARGETS = {
    "C56-01": ["CLO56A001"],
    "C56-02": ["CLO56A002"],
    "C56-03": ["CLO56A003"],
    "C56-04": ["CLO56A007"],
    "C56-05": ["CLO56A004"],
    "C56-06": ["CLO56A004"],
    "C56-07": ["CLO56A008"],
    "C56-08": ["CLO56A005"],
    "C56-09": ["CLO56A006"],
    "C56-10": ["CLO56A009"],
    "C56-11": ["CLO56A010"],
    "C56-12": ["CLO56A012"],
    "C56-13": ["CLO56A013"],
    "C56-14": ["CLO56A011"],
    "C56-15": ["CLO56A014"],
    "C56-16": ["CLO56A015", "CLO56A016"],
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def source_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not IGNORED_PARTS.intersection(path.parts)
        and path.suffix != ".pyc"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n?", content, re.DOTALL)
    if match is None:
        fail(f"invalid Skill frontmatter: {path}")
    frontmatter = yaml.safe_load(match.group(1))
    if not isinstance(frontmatter, dict):
        fail(f"Skill frontmatter must be an object: {path}")
    return frontmatter, content[match.end() :].lstrip("\n")


def write_exact(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_file() and path.read_bytes() == content:
            return
        fail(f"refusing to overwrite a different file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_json_exact(path: Path, value: Any) -> None:
    write_exact(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def canonical_source_inventory(root: Path) -> dict[str, Any]:
    files = source_files(root)
    return {
        "schema_version": "1.0",
        "source_package": "elmos-codex-skills-batch56-product-closure",
        "file_count": len(files),
        "files": [
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": "sha256:" + sha256_file(path),
                "bytes": path.stat().st_size,
            }
            for path in files
        ],
    }


def validate_source(root: Path) -> list[dict[str, Any]]:
    if not root.is_dir():
        fail(f"Batch 56 source package is missing: {root}")
    if any(path.is_symlink() for path in root.rglob("*")):
        fail("Batch 56 source package may not contain symbolic links")
    inventory = canonical_source_inventory(root)
    if inventory["file_count"] != EXPECTED_SOURCE_FILE_COUNT:
        fail(
            f"Batch 56 source must contain exactly {EXPECTED_SOURCE_FILE_COUNT} files; "
            f"found {inventory['file_count']}"
        )
    manifest = load_json(root / "manifest.json")
    skills = manifest.get("skills")
    if (
        manifest.get("batch") != "56"
        or manifest.get("title") != "ELMOS Product Closure & Consolidation"
        or manifest.get("skill_count") != 16
        or not isinstance(skills, list)
        or len(skills) != 16
        or [item.get("id") for item in skills] != EXPECTED_IDS
    ):
        fail("Batch 56 manifest identity, count or ordered IDs are invalid")
    seen_names: set[str] = set()
    invalid_source_ids: set[str] = set()
    for item in skills:
        source_id = item["id"]
        name = item.get("name")
        relative = item.get("path")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z0-9-]+", name)
            or name in seen_names
            or not isinstance(relative, str)
            or relative != f"agent-skills/runtime/{name}/SKILL.md"
            or item.get("maturity") != "reviewed-implementation-guidance"
        ):
            fail(f"invalid Batch 56 Skill manifest entry: {source_id}")
        source = (root / relative).resolve()
        try:
            source.relative_to(root.resolve())
        except ValueError:
            fail(f"Batch 56 Skill path escapes package root: {source_id}")
        if not source.is_file():
            fail(f"missing Batch 56 Skill source: {source_id}")
        frontmatter, body = parse_frontmatter(source)
        if frontmatter.get("name") != name or not isinstance(frontmatter.get("description"), str):
            fail(f"Batch 56 Skill frontmatter identity mismatch: {source_id}")
        required_sections = (
            "## Objective",
            "## Scope",
            "## Preconditions",
            "## Workflow",
            "## Required Outputs",
            "## Required Tests",
            "## Verification",
            "## Stop and Escalate",
            "## Definition of Done",
            "## Completion Report",
        )
        if any(section not in body for section in required_sections):
            fail(f"Batch 56 Skill is missing a required section: {source_id}")
        valid, _ = skill_creator_tools.validate_skill(source.parent)
        if not valid:
            invalid_source_ids.add(source_id)
        seen_names.add(name)
    if invalid_source_ids != INVALID_SOURCE_NAME_IDS:
        fail(
            "unexpected Codex source-validation result; "
            f"expected={sorted(INVALID_SOURCE_NAME_IDS)} actual={sorted(invalid_source_ids)}"
        )
    if set(OVERLAP_TARGETS) != set(EXPECTED_IDS):
        fail("Batch 56 overlap map must cover all exact source IDs")
    return skills


def alias_for(source_name: str) -> str:
    candidate = f"b56-{source_name}"
    if len(candidate) <= skill_creator_tools.MAX_SKILL_NAME_LENGTH:
        return candidate
    suffix = hashlib.sha256(source_name.encode()).hexdigest()[:8]
    prefix_length = skill_creator_tools.MAX_SKILL_NAME_LENGTH - len(suffix) - 1
    prefix = candidate[:prefix_length].rstrip("-")
    return f"{prefix}-{suffix}"


def expected_interface(alias: str) -> str:
    display_name = skill_creator_tools.format_display_name(alias)
    short_description = "Run this Product Batch 56 guidance Skill safely"
    default_prompt = (
        f"Use ${alias} as inactive Product Batch 56 guidance; preserve Product 56A "
        "authority and fail closed on missing evidence."
    )
    return "\n".join(
        [
            "interface:",
            f"  display_name: {skill_creator_tools.yaml_quote(display_name)}",
            f"  short_description: {skill_creator_tools.yaml_quote(short_description)}",
            f"  default_prompt: {skill_creator_tools.yaml_quote(default_prompt)}",
            "",
        ]
    )


def normalized_skill(root: Path, item: dict[str, Any]) -> bytes:
    source = root / item["path"]
    frontmatter, body = parse_frontmatter(source)
    alias = alias_for(item["name"])
    normalized = {
        "name": alias,
        "description": frontmatter["description"],
        "metadata": {
            "source_package": "elmos-codex-skills-batch56-product-closure",
            "source_id": item["id"],
            "source_name": item["name"],
            "source_batch": "56",
            "source_maturity": "reviewed-implementation-guidance",
            "source_sha256": "sha256:" + sha256_file(source),
            "normalized_namespace": "product-batch56-reviewed-guidance",
            "activation_default": "inactive",
            "readiness_authority": "product-batch56a",
        },
    }
    boundary = "\n".join(
        [
            "",
            "## Repository Integration Boundary",
            "",
            "- This installed Skill is reviewed implementation guidance, not evidence that the capability exists.",
            "- Its activation default is `inactive` because Product 56A already owns the overlapping closure capability.",
            f"- Source identity remains `{item['id']}` / `{item['name']}`; the installed alias only resolves naming constraints.",
            "- Product readiness authority remains `scripts/product-closure-batch56a/run_product_closure_gate.py`.",
            "- `NOT_RUN`, unknown, partial, synthetic or self-verified evidence is non-success.",
            "- This Skill cannot approve GA, production certification, deployment or customer acceptance.",
            "",
        ]
    )
    rendered = (
        "---\n"
        + yaml.safe_dump(normalized, allow_unicode=True, sort_keys=False).strip()
        + "\n---\n\n"
        + body.rstrip()
        + "\n"
        + boundary
    )
    return rendered.encode()


def expected_overlap_map(skills: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "namespace": "product-batch56-reviewed-guidance",
        "activation_default": "inactive",
        "readiness_authority": "scripts/product-closure-batch56a/run_product_closure_gate.py",
        "relationships": [
            {
                "source_id": item["id"],
                "source_name": item["name"],
                "installed_alias": alias_for(item["name"]),
                "relationship": "supplementary-overlap",
                "product_56a_source_ids": OVERLAP_TARGETS[item["id"]],
            }
            for item in skills
        ],
    }


def expected_installed_manifest(root: Path, skills: list[dict[str, Any]]) -> dict[str, Any]:
    records = []
    for item in skills:
        alias = alias_for(item["name"])
        source = root / item["path"]
        installed = RUNTIME / alias / "SKILL.md"
        interface = installed.parent / "agents" / "openai.yaml"
        records.append(
            {
                "source_id": item["id"],
                "source_name": item["name"],
                "source_path": source.relative_to(ROOT).as_posix(),
                "source_sha256": "sha256:" + sha256_file(source),
                "source_maturity": "reviewed-implementation-guidance",
                "installed_alias": alias,
                "installed_path": installed.relative_to(ROOT).as_posix(),
                "installed_sha256": "sha256:" + sha256_file(installed),
                "interface_sha256": "sha256:" + sha256_file(interface),
                "activation_default": "inactive",
                "overlap_with_product_56a": OVERLAP_TARGETS[item["id"]],
            }
        )
    return {
        "schema_version": "1.0",
        "source_package": "elmos-codex-skills-batch56-product-closure",
        "source_namespace": "product-batch56-reviewed-guidance",
        "skill_count": 16,
        "skills": records,
        "source_skill_validation": {
            "contract": "repository-pinned-skill-creator-compatible",
            "valid": 11,
            "invalid_name_length": 5,
            "normalized_installed_valid": 16,
        },
        "exact_runtime_name_collisions_before_aliasing": [
            "canonical-domain-kernel-consolidation"
        ],
        "activation_default": "inactive",
        "readiness_authority": "scripts/product-closure-batch56a/run_product_closure_gate.py",
        "maximum_local_decision": "READY_FOR_EXTERNAL_GATE",
        "external_evidence": "NOT_RUN",
        "ga_approved": False,
        "production_certified": False,
    }


def import_source(source: Path) -> None:
    validate_source(source)
    if source.resolve() == CANONICAL.resolve():
        return
    for path in source_files(source):
        destination = CANONICAL / path.relative_to(source)
        write_exact(destination, path.read_bytes())
        destination.chmod(path.stat().st_mode & 0o777)


def install() -> None:
    skills = validate_source(CANONICAL)
    aliases = [alias_for(item["name"]) for item in skills]
    if len(set(aliases)) != 16 or any(
        len(alias) > skill_creator_tools.MAX_SKILL_NAME_LENGTH for alias in aliases
    ):
        fail("Batch 56 deterministic aliases are not unique Codex names")
    for item in skills:
        alias = alias_for(item["name"])
        target = RUNTIME / alias
        write_exact(target / "SKILL.md", normalized_skill(CANONICAL, item))
        write_exact(target / "agents" / "openai.yaml", expected_interface(alias).encode())
    write_exact(
        ROOT / "templates" / "product-closure-batch56" / "closure-program-status.source.json",
        (CANONICAL / "templates" / "closure-program-status.json").read_bytes(),
    )
    for directory in ("docs", "references"):
        for source in source_files(CANONICAL / directory):
            write_exact(
                DOC_ROOT / "source" / directory / source.relative_to(CANONICAL / directory),
                source.read_bytes(),
            )
    write_json_exact(SOURCE_INVENTORY, canonical_source_inventory(CANONICAL))
    write_json_exact(OVERLAP_MAP, expected_overlap_map(skills))
    write_json_exact(INSTALLED_MANIFEST, expected_installed_manifest(CANONICAL, skills))
    verify()


def verify() -> None:
    skills = validate_source(CANONICAL)
    aliases = [alias_for(item["name"]) for item in skills]
    if len(set(aliases)) != 16:
        fail("Batch 56 deterministic aliases are not unique")
    for item in skills:
        alias = alias_for(item["name"])
        target = RUNTIME / alias
        if (target / "SKILL.md").read_bytes() != normalized_skill(CANONICAL, item):
            fail(f"installed Batch 56 Skill is missing or changed: {alias}")
        valid, message = skill_creator_tools.validate_skill(target)
        if not valid:
            fail(f"installed Batch 56 Skill is invalid: {alias}: {message}")
        if (target / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        ) != expected_interface(alias):
            fail(f"installed Batch 56 interface is missing or changed: {alias}")
    if load_json(SOURCE_INVENTORY) != canonical_source_inventory(CANONICAL):
        fail("Batch 56 source inventory is missing or stale")
    if load_json(OVERLAP_MAP) != expected_overlap_map(skills):
        fail("Batch 56 overlap map is missing or stale")
    if load_json(INSTALLED_MANIFEST) != expected_installed_manifest(CANONICAL, skills):
        fail("Batch 56 installed manifest is missing or stale")
    print(
        json.dumps(
            {
                "status": "PASS",
                "source_files": EXPECTED_SOURCE_FILE_COUNT,
                "source_skills": 16,
                "source_skill_creator_compatible_valid": 11,
                "source_name_length_invalid": 5,
                "installed_skills_valid": 16,
                "interfaces_valid": 16,
                "activation_default": "inactive",
                "readiness_authority": "product-batch56a",
                "external_evidence": "NOT_RUN",
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--import-source", type=Path)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    if args.import_source:
        import_source(args.import_source.resolve())
    if args.install:
        install()
    else:
        verify()


if __name__ == "__main__":
    main()
