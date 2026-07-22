#!/usr/bin/env python3
"""Normalize and install the submitted Product B40-B55 Codex Skill pack."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import Counter
from pathlib import Path

from integrate_product_batch34_38_complete_skill_packs import (
    ROOT,
    RUNTIME,
    digest,
    generate_interface,
    installed_name,
    load_official_validator,
)


PACK = ROOT / "elmos-codex-skills-batch40-55-complete"
MANIFEST = PACK / "manifest.json"
PRIOR_LEGACY = ROOT / "docs" / "product-batches33-38" / "skill-source-manifest.json"
PRIOR_COMPLETE = ROOT / "docs" / "product-batches34-38-complete" / "skill-source-manifest.json"
PRIOR_B39 = ROOT / "docs" / "product-batches39-complete" / "skill-source-manifest.json"
OUTPUT = ROOT / "docs" / "product-batches40-55-complete" / "skill-source-manifest.json"
TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".py", ".sh"}
EXPECTED_BATCHES = {str(batch): 48 for batch in range(40, 56)}
EXPECTED_SUBBATCHES = {
    f"{batch}{suffix}": 16
    for batch in range(40, 56)
    for suffix in ("A", "B", "C")
}


def tree_digest(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        value.update(str(path.relative_to(root)).encode("utf-8"))
        value.update(b"\0")
        value.update(path.read_bytes())
        value.update(b"\0")
    return value.hexdigest()


def replace_references(aliases: dict[str, str]) -> None:
    replacements = {
        source: target for source, target in aliases.items() if source != target
    }
    if not replacements:
        return
    expression = re.compile(
        "|".join(re.escape(name) for name in sorted(replacements, key=len, reverse=True))
    )
    for path in PACK.rglob("*"):
        if (
            not path.is_file()
            or path == MANIFEST
            or path.suffix.lower() not in TEXT_SUFFIXES
        ):
            continue
        content = path.read_text(encoding="utf-8")
        updated = expression.sub(lambda match: replacements[match.group(0)], content)
        if updated != content:
            path.write_text(updated, encoding="utf-8")


def prior_product_names() -> set[str]:
    names: set[str] = set()
    for manifest in (PRIOR_LEGACY, PRIOR_COMPLETE, PRIOR_B39):
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        names.update(record["name"] for record in payload["records"])
    if len(names) != 339:
        raise SystemExit(f"Expected 339 canonical Product Skills through B39, found {len(names)}")
    return names


def previously_owned_names() -> set[str]:
    if not OUTPUT.is_file():
        return set()
    return {
        record["name"]
        for record in json.loads(OUTPUT.read_text(encoding="utf-8"))["records"]
    }


def interface_is_current(skill_dir: Path, name: str) -> bool:
    interface = skill_dir / "agents" / "openai.yaml"
    if not interface.is_file():
        return False
    content = interface.read_text(encoding="utf-8")
    return "default_prompt:" in content and f"${name}" in content


def main() -> None:
    validate_skill = load_official_validator()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    items = manifest.get("skills", [])
    if manifest.get("skillCount") != 768 or len(items) != 768:
        raise SystemExit("Product B40-B55 complete pack must contain exactly 768 Skills")
    batch_counts = Counter(str(item["batch"]) for item in items)
    subbatch_counts = Counter(item["subbatch"] for item in items)
    if dict(batch_counts) != EXPECTED_BATCHES:
        raise SystemExit(f"Unexpected Product B40-B55 batch counts: {dict(batch_counts)}")
    if dict(subbatch_counts) != EXPECTED_SUBBATCHES:
        raise SystemExit(f"Unexpected Product B40-B55 subbatch counts: {dict(subbatch_counts)}")
    provenance_counts = Counter(item["provenance"] for item in items)
    if provenance_counts != {
        "approved-conversation-design": 16,
        "generated-planning-edition": 752,
    }:
        raise SystemExit(f"Unexpected Product B40-B55 provenance: {dict(provenance_counts)}")

    source_tree_sha256 = manifest.get("sourcePackageTreeSha256", tree_digest(PACK))
    source_manifest_sha256 = manifest.get(
        "sourceManifestSha256", digest(MANIFEST.read_bytes())
    )
    package_version = manifest.get("version", "4.0-5.5-complete")

    aliases: dict[str, str] = {}
    for item in items:
        source_name = item.get("source_name", item["name"])
        name = installed_name(source_name)
        aliases[source_name] = name
        aliases[item["name"]] = name
    normalized_names = [installed_name(item.get("source_name", item["name"])) for item in items]
    if len(normalized_names) != len(set(normalized_names)):
        raise SystemExit("Product B40-B55 normalized Skill name collision")

    prior_names = prior_product_names()
    overlaps = sorted(prior_names.intersection(normalized_names))
    if overlaps:
        raise SystemExit(f"Product B40-B55 collides with prior Product Skills: {overlaps}")

    replace_references(aliases)
    owned = previously_owned_names()
    records: list[dict[str, object]] = []
    renamed = 0
    for item in items:
        source_name = item.get("source_name", item["name"])
        name = installed_name(source_name)
        old_dir = (PACK / item["path"]).parent
        new_dir = PACK / "agent-skills" / "runtime" / name
        if old_dir != new_dir:
            if new_dir.exists():
                raise SystemExit(f"Normalized target already exists: {new_dir}")
            old_dir.rename(new_dir)

        skill_path = new_dir / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        updated = re.sub(r"(?m)^name:\s*[^\n]+$", f"name: {name}", skill, count=1)
        if updated == skill and not re.search(rf"(?m)^name:\s*{re.escape(name)}$", skill):
            raise SystemExit(f"Cannot normalize frontmatter for {source_name}")
        skill_path.write_text(updated, encoding="utf-8")
        product_batch = int(item["batch"])
        if not interface_is_current(new_dir, name):
            generate_interface(new_dir, product_batch, source_name, name)
        valid, message = validate_skill(new_dir)
        if not valid:
            raise SystemExit(f"Official validation failed for {name}: {message}")

        target_dir = RUNTIME / name
        if target_dir.exists() and name not in owned:
            raise SystemExit(f"Refusing to overwrite non-B40-B55 Runtime Skill: {name}")
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_path, target_dir / "SKILL.md")
        (target_dir / "agents").mkdir(parents=True, exist_ok=True)
        shutil.copy2(new_dir / "agents" / "openai.yaml", target_dir / "agents" / "openai.yaml")
        valid, message = validate_skill(target_dir)
        if not valid:
            raise SystemExit(f"Installed Product B40-B55 Skill is invalid: {name}: {message}")

        item["source_name"] = source_name
        item["name"] = name
        item["path"] = f"agent-skills/runtime/{name}/SKILL.md"
        if source_name != name:
            renamed += 1
        records.append(
            {
                "family": "elmos-product-commercialization-b40-b55-complete",
                "product_batch": product_batch,
                "batch": str(item["batch"]),
                "subbatch": item["subbatch"],
                "provenance": item["provenance"],
                "package_version": package_version,
                "name": name,
                "source_name": source_name,
                "source_path": f"{PACK.name}/{item['path']}",
                "sha256": digest(skill_path.read_bytes()),
            }
        )

    for details in manifest["subbatches"].values():
        details["skills"] = [aliases.get(value, value) for value in details["skills"]]
    manifest["version"] = package_version
    manifest["sourceManifestSha256"] = source_manifest_sha256
    manifest["sourcePackageTreeSha256"] = source_tree_sha256
    manifest["nameNormalization"] = {
        "maximumLength": 64,
        "algorithm": "source name when <=64, otherwise first 55 characters plus '-' plus sha256[:8]",
        "renamed": renamed,
        "sourceNamePreserved": True,
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    canonical = prior_names.union(normalized_names)
    if len(canonical) != 1107 or renamed != 456:
        raise SystemExit(
            f"Expected 1,107 canonical Product Skills and 456 aliases; found {len(canonical)} and {renamed}"
        )
    runtime_total = len(list(RUNTIME.glob("*/SKILL.md")))
    if runtime_total != 1647:
        raise SystemExit(f"Expected 1,647 Runtime Skills after Product B40-B55, found {runtime_total}")

    payload = {
        "namespace_policy": {
            "product_commercialization": "Product Batch B40-B55 Enterprise Domains",
            "migration_pack": "Migration Packs M40-M45",
        },
        "generated_by": "tooling/integrate_product_batch40_55_complete_skill_pack.py",
        "external_execution_evidence": "NOT_RUN",
        "pack_skill_count": 768,
        "approved_conversation_design_count": 16,
        "generated_planning_edition_count": 752,
        "canonical_product_skill_count_with_prior_families": len(canonical),
        "superseded_prior_record_count": 0,
        "superseded_prior_records": [],
        "packages": [
            {
                "product_batches": "40-55",
                "directory": PACK.name,
                "version": package_version,
                "skill_count": len(records),
                "renamed_for_codex": renamed,
                "source_manifest_sha256": source_manifest_sha256,
                "source_package_tree_sha256": source_tree_sha256,
                "normalized_manifest_sha256": digest(MANIFEST.read_bytes()),
            }
        ],
        "records": records,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "complete_pack_skills": len(records),
                "batch_counts": dict(batch_counts),
                "subbatch_count": len(subbatch_counts),
                "normalized_names": renamed,
                "approved_conversation_design": provenance_counts["approved-conversation-design"],
                "generated_planning_edition": provenance_counts["generated-planning-edition"],
                "superseded_prior_records": 0,
                "canonical_product_skills": len(canonical),
                "runtime_skill_total": runtime_total,
                "external_execution_evidence": "NOT_RUN",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
