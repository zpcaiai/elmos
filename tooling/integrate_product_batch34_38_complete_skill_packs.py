#!/usr/bin/env python3
"""Normalize and install the complete Product B34-B38 Codex Skill packs.

The submitted packs are kept as self-contained distributable directories.  A
stable alias is used when a source Skill name exceeds Codex's 64-character
limit.  The original name remains in each package manifest as ``source_name``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "agent-skills" / "runtime"
OUTPUT = ROOT / "docs" / "product-batches34-38-complete" / "skill-source-manifest.json"
LEGACY_MANIFEST = ROOT / "docs" / "product-batches33-38" / "skill-source-manifest.json"
SKILL_CREATOR = Path("/Users/stephen/.codex/skills/.system/skill-creator")
GENERATE_YAML = SKILL_CREATOR / "scripts" / "generate_openai_yaml.py"
OFFICIAL_VALIDATOR = SKILL_CREATOR / "scripts" / "quick_validate.py"
PACK_BATCHES = range(34, 39)
EXPECTED_COUNTS = {34: 18, 35: 33, 36: 41, 37: 48, 38: 48, 39: 48}
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".sh"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installed_name(source_name: str) -> str:
    if len(source_name) <= 64:
        return source_name
    suffix = digest(source_name.encode("utf-8"))[:8]
    return f"{source_name[:55].rstrip('-')}-{suffix}"


def load_official_validator():
    spec = importlib.util.spec_from_file_location("elmos_complete_pack_validator", OFFICIAL_VALIDATOR)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load official Skill validator: {OFFICIAL_VALIDATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_skill


def replace_skill_names(pack: Path, aliases: dict[str, str]) -> None:
    replacements = [(source, target) for source, target in aliases.items() if source != target]
    if not replacements:
        return
    for path in pack.rglob("*"):
        if not path.is_file() or path.name == "manifest.json" or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = path.read_text(encoding="utf-8")
        updated = content
        for source, target in replacements:
            updated = updated.replace(source, target)
        if updated != content:
            path.write_text(updated, encoding="utf-8")


def generate_interface(skill_dir: Path, product_batch: int, source_name: str, name: str) -> None:
    display = f"ELMOS Product B{product_batch}: {source_name.replace('-', ' ').title()}"
    short = f"Run ELMOS Product B{product_batch} contract with fail-closed evidence"
    prompt = f"Use ${name} to implement its fail-closed ELMOS Product B{product_batch} contract."
    subprocess.run(
        [
            sys.executable,
            str(GENERATE_YAML),
            str(skill_dir),
            "--interface",
            f"display_name={display}",
            "--interface",
            f"short_description={short}",
            "--interface",
            f"default_prompt={prompt}",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def normalize_pack(product_batch: int, validate_skill) -> tuple[dict[str, object], list[dict[str, object]]]:
    pack = ROOT / f"elmos-codex-skills-batch{product_batch}-complete"
    manifest_path = pack / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(f"Missing complete Skill pack manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("skills", [])
    declared_count = manifest.get("skill_count", manifest.get("skillCount"))
    if declared_count != EXPECTED_COUNTS[product_batch] or len(items) != EXPECTED_COUNTS[product_batch]:
        raise SystemExit(f"Product B{product_batch}: expected {EXPECTED_COUNTS[product_batch]} Skills")
    package_version = manifest.get("version", f"3.{product_batch % 10}-complete")
    manifest.setdefault("version", package_version)

    aliases: dict[str, str] = {}
    for item in items:
        source_name = item.get("source_name", item["name"])
        name = installed_name(source_name)
        aliases[source_name] = name
        aliases[item["name"]] = name
    canonical = [installed_name(item.get("source_name", item["name"])) for item in items]
    if len(canonical) != len(set(canonical)):
        raise SystemExit(f"Product B{product_batch}: normalized Skill name collision")

    replace_skill_names(pack, aliases)
    records: list[dict[str, object]] = []
    renamed = 0
    for item in items:
        source_name = item.get("source_name", item["name"])
        name = installed_name(source_name)
        old_path = pack / item["path"]
        old_dir = old_path.parent
        new_dir = pack / "agent-skills" / "runtime" / name
        if old_dir != new_dir:
            if new_dir.exists():
                raise SystemExit(f"Product B{product_batch}: normalized target already exists: {new_dir}")
            old_dir.rename(new_dir)
        skill_path = new_dir / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        updated = re.sub(r"(?m)^name:\s*[^\n]+$", f"name: {name}", skill, count=1)
        if updated == skill and not re.search(rf"(?m)^name:\s*{re.escape(name)}$", skill):
            raise SystemExit(f"Product B{product_batch}: cannot normalize frontmatter for {source_name}")
        skill_path.write_text(updated, encoding="utf-8")
        generate_interface(new_dir, product_batch, source_name, name)

        valid, message = validate_skill(new_dir)
        if not valid:
            raise SystemExit(f"Product B{product_batch}: official validation failed for {name}: {message}")
        interface = (new_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
        if f"${name}" not in interface:
            raise SystemExit(f"Product B{product_batch}: interface does not invoke ${name}")

        item["source_name"] = source_name
        item["name"] = name
        item["path"] = f"agent-skills/runtime/{name}/SKILL.md"
        if source_name != name:
            renamed += 1
        records.append(
            {
                "family": "elmos-product-commercialization-complete",
                "product_batch": product_batch,
                "batch": item["batch"],
                "package_version": package_version,
                "name": name,
                "source_name": source_name,
                "source_path": f"{pack.name}/{item['path']}",
                "sha256": digest(skill_path.read_bytes()),
            }
        )

    for details in manifest.get("batches", {}).values():
        details["skills"] = [aliases.get(value, value) for value in details.get("skills", [])]
    manifest["name_normalization"] = {
        "maximum_length": 64,
        "algorithm": "source name when <=64, otherwise first 55 characters plus '-' plus sha256[:8]",
        "renamed": renamed,
        "source_name_preserved": True,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    for record in records:
        source_dir = pack / Path(record["source_path"]).relative_to(pack.name).parent
        target_dir = RUNTIME / record["name"]
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir / "SKILL.md", target_dir / "SKILL.md")
        (target_dir / "agents").mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir / "agents" / "openai.yaml", target_dir / "agents" / "openai.yaml")
        valid, message = validate_skill(target_dir)
        if not valid:
            raise SystemExit(f"Installed Product B{product_batch} Skill is invalid: {record['name']}: {message}")

    package_record = {
        "product_batch": product_batch,
        "directory": pack.name,
        "version": package_version,
        "skill_count": len(records),
        "renamed_for_codex": renamed,
        "manifest_sha256": digest(manifest_path.read_bytes()),
    }
    return package_record, records


def main() -> None:
    if not GENERATE_YAML.is_file() or not OFFICIAL_VALIDATOR.is_file():
        raise SystemExit("The official skill-creator tools are required")
    validate_skill = load_official_validator()
    packages: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    for product_batch in PACK_BATCHES:
        package, package_records = normalize_pack(product_batch, validate_skill)
        packages.append(package)
        records.extend(package_records)

    names = [record["name"] for record in records]
    if len(records) != 188 or len(names) != len(set(names)):
        raise SystemExit("Complete Product B34-B38 catalog must contain 188 unique Skills")
    legacy = json.loads(LEGACY_MANIFEST.read_text(encoding="utf-8"))["records"]
    legacy_names = {record["name"] for record in legacy}
    superseded = sorted(legacy_names.intersection(names))
    canonical_names = legacy_names.union(names)
    if len(canonical_names) != 291:
        raise SystemExit(f"Expected 291 canonical legacy-plus-complete names, found {len(canonical_names)}")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "namespace_policy": {
            "product_commercialization": "Product Batch B34-B38 Complete",
            "migration_pack": "Migration Pack M35-M45",
        },
        "generated_by": "tooling/integrate_product_batch34_38_complete_skill_packs.py",
        "external_execution_evidence": "NOT_RUN",
        "pack_skill_count": len(records),
        "canonical_product_skill_count_with_legacy_b33_b38": len(canonical_names),
        "superseded_legacy_record_count": len(superseded),
        "superseded_legacy_records": superseded,
        "packages": packages,
        "records": records,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "complete_pack_skills": len(records),
                "normalized_names": sum(package["renamed_for_codex"] for package in packages),
                "superseded_legacy_records": len(superseded),
                "canonical_product_skills": len(canonical_names),
                "runtime_skill_total": len(list(RUNTIME.glob("*/SKILL.md"))),
                "by_product_batch": dict(Counter(record["product_batch"] for record in records)),
                "external_execution_evidence": "NOT_RUN",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
