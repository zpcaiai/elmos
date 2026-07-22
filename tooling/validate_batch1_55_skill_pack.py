#!/usr/bin/env python3
"""Validate the normalized ELMOS M1-M45 and Product B34-B55 Skill pack."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACK = ROOT / "elmos-codex-skills-batch1-55-complete"
OFFICIAL_VALIDATOR = Path(
    "/Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py"
)

MIGRATION_COUNTS = {
    **{batch: 16 for batch in range(1, 29)},
    29: 20,
    30: 20,
    31: 22,
    32: 20,
    33: 20,
    34: 22,
    35: 22,
    36: 18,
    37: 36,
    38: 22,
    39: 22,
    40: 24,
    41: 20,
    42: 22,
    43: 20,
    44: 20,
    45: 22,
}
PRODUCT_COUNTS = {
    34: 18,
    35: 33,
    36: 41,
    **{batch: 48 for batch in range(37, 56)},
}
PROVENANCE_COUNTS = {
    "normalized-batch1-28": 448,
    "imported-original-batch29-33": 102,
    "repository-migration-pack-m34-m45": 270,
    "imported-complete-batch34-38": 188,
    "imported-complete-batch39": 48,
    "approved-conversation-design": 16,
    "generated-planning-edition": 752,
}
EDITION_COUNTS = {
    "normalized-source-incomplete": 448,
    "repository-contract": 372,
    "complete-source-contract": 236,
    "approved-conversation-design": 16,
    "generated-planning-edition": 752,
}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installed_name(source_name: str) -> str:
    if len(source_name) <= 64:
        return source_name
    return f"{source_name[:55].rstrip('-')}-{digest(source_name.encode())[:8]}"


def load_official_validator():
    if not OFFICIAL_VALIDATOR.is_file():
        fail(f"official skill-creator validator is missing: {OFFICIAL_VALIDATOR}")
    spec = importlib.util.spec_from_file_location("elmos_batch1_55_validator", OFFICIAL_VALIDATOR)
    if spec is None or spec.loader is None:
        fail("cannot load official skill-creator validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_skill


def validate_interface(skill_dir: Path, name: str) -> None:
    path = skill_dir / "agents" / "openai.yaml"
    if not path.is_file():
        fail(f"missing agents/openai.yaml: {name}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        fail(f"invalid agents/openai.yaml for {name}: {exc}")
    interface = payload.get("interface") if isinstance(payload, dict) else None
    if not isinstance(interface, dict):
        fail(f"missing interface mapping for {name}")
    for key in ("display_name", "short_description", "default_prompt"):
        if not isinstance(interface.get(key), str) or not interface[key].strip():
            fail(f"missing interface.{key} for {name}")
    if not 25 <= len(interface["short_description"]) <= 64:
        fail(f"interface.short_description length is invalid for {name}")
    if f"${name}" not in interface["default_prompt"]:
        fail(f"default_prompt does not invoke ${name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pack", nargs="?", type=Path, default=DEFAULT_PACK)
    args = parser.parse_args()
    pack = args.pack.resolve()
    manifest_path = pack / "manifest.json"
    if not manifest_path.is_file():
        fail(f"manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("skills", [])
    if manifest.get("schemaVersion") != "2":
        fail("manifest schemaVersion must be 2")
    if manifest.get("skillCount") != 1824 or len(records) != 1824:
        fail(f"expected 1,824 Skills, found {len(records)}")
    if manifest.get("externalEvidenceStatus") != "NOT_RUN":
        fail("external evidence must remain NOT_RUN")
    completion = manifest.get("completion", {})
    if completion.get("overall") != "NOT_COMPLETE":
        fail("overall completion must remain NOT_COMPLETE while source/planning blockers exist")
    if completion.get("structural") != "PASS":
        fail("structural completion must be PASS after normalization")

    namespace_counts: dict[str, Counter[int]] = defaultdict(Counter)
    provenance = Counter()
    editions = Counter()
    names: set[str] = set()
    source_keys: set[tuple[str, str]] = set()
    official_validate = load_official_validator()
    official_valid = 0
    renamed = 0

    for record in records:
        name = record.get("name")
        source_name = record.get("source_name")
        namespace = record.get("namespace")
        batch = record.get("batch")
        if not isinstance(name, str) or not isinstance(source_name, str):
            fail("record name/source_name must be strings")
        if name != installed_name(source_name):
            fail(f"non-deterministic alias for {source_name}: {name}")
        if len(name) > 64:
            fail(f"Skill name exceeds 64 characters: {name}")
        if name in names:
            fail(f"duplicate installed Skill name: {name}")
        names.add(name)
        source_key = (namespace, source_name)
        if source_key in source_keys:
            fail(f"duplicate source Skill identity: {source_key}")
        source_keys.add(source_key)
        if namespace not in {"migration-pack", "product-commercialization"}:
            fail(f"invalid namespace for {name}: {namespace}")
        if not isinstance(batch, int):
            fail(f"batch must be an integer for {name}")
        namespace_counts[namespace][batch] += 1
        provenance[record.get("provenance")] += 1
        editions[record.get("editionStatus")] += 1
        renamed += name != source_name

        expected_path = f"agent-skills/runtime/{name}/SKILL.md"
        if record.get("path") != expected_path:
            fail(f"manifest path mismatch for {name}")
        skill_path = pack / expected_path
        if not skill_path.is_file():
            fail(f"missing Skill file: {skill_path}")
        if digest(skill_path.read_bytes()) != record.get("sha256"):
            fail(f"Skill digest mismatch: {name}")
        front_name = re.search(
            r"(?m)^name:\s*([^\n]+)$", skill_path.read_text(encoding="utf-8")
        )
        if front_name is None or front_name.group(1).strip() != name:
            fail(f"frontmatter/directory mismatch for {name}")
        valid, message = official_validate(skill_path.parent)
        if not valid:
            fail(f"official Skill validation failed for {name}: {message}")
        official_valid += 1
        validate_interface(skill_path.parent, name)

    if dict(namespace_counts["migration-pack"]) != MIGRATION_COUNTS:
        fail(f"migration namespace counts drifted: {dict(namespace_counts['migration-pack'])}")
    if dict(namespace_counts["product-commercialization"]) != PRODUCT_COUNTS:
        fail(f"product namespace counts drifted: {dict(namespace_counts['product-commercialization'])}")
    if dict(provenance) != PROVENANCE_COUNTS:
        fail(f"provenance counts drifted: {dict(provenance)}")
    if dict(editions) != EDITION_COUNTS:
        fail(f"edition counts drifted: {dict(editions)}")
    declared_namespace_counts = manifest.get("namespaceCounts", {})
    if declared_namespace_counts != {"migration-pack": 820, "product-commercialization": 1004}:
        fail(f"namespace totals drifted: {declared_namespace_counts}")
    normalization = manifest.get("nameNormalization", {})
    if normalization.get("renamed") != renamed or normalization.get("maximumLength") != 64:
        fail("name-normalization metadata drifted")
    if renamed != 1015:
        fail(f"expected 1,015 deterministic aliases, found {renamed}")

    disk_skills = list((pack / "agent-skills" / "runtime").glob("*/SKILL.md"))
    if len(disk_skills) != len(records):
        fail(f"unexpected on-disk Skill inventory: {len(disk_skills)}")

    print(
        json.dumps(
            {
                "structural_status": "PASS",
                "overall_completion": "NOT_COMPLETE",
                "official_skill_validation": {"valid": official_valid, "failed": 0},
                "interfaces": {"valid": official_valid, "failed": 0},
                "namespace_counts": manifest["namespaceCounts"],
                "migration_batch_range": "M1-M45",
                "product_batch_range": "B34-B55",
                "deterministic_aliases": renamed,
                "source_incomplete": editions["normalized-source-incomplete"],
                "planning_edition": editions["generated-planning-edition"],
                "external_evidence": "NOT_RUN",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
