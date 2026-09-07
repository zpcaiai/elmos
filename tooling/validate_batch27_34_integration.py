#!/usr/bin/env python3
"""Aggregate structural validation for product B27-34 and Migration Packs M29-M34."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUICK_VALIDATE = Path("/Users/stephen/.codex/skills/.system/skill-creator/scripts/quick_validate.py")


def main() -> None:
    manifest_path = ROOT / "docs" / "product-batches27-34" / "skill-source-manifest.json"
    records = json.loads(manifest_path.read_text(encoding="utf-8"))["records"]
    assert len(records) == 289, len(records)
    counts = Counter(str(record["batch"]) for record in records)
    assert counts == Counter({
        "M29": 20, "M30": 20, "M31": 22, "M32": 20, "M33": 20, "M34": 22,
        "27": 18, "28": 18, "29": 18, "30": 18, "31": 18, "33": 35, "34": 40,
    }), counts
    installed_names: set[str] = set()
    for record in records:
        name = record["name"]
        assert name not in installed_names, name
        installed_names.add(name)
        skill_dir = ROOT / "agent-skills" / "runtime" / name
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert re.match(rf"^---\nname: {re.escape(name)}\ndescription: ", skill), name
        interface = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert f"${name}" in interface, name
        subprocess.run([sys.executable, str(QUICK_VALIDATE), str(skill_dir)], check=True,
                       stdout=subprocess.DEVNULL)
    assert len(list((ROOT / "agent-skills" / "runtime").glob("*/SKILL.md"))) == 615
    schemas = sum(len(list((ROOT / "schemas" / f"batch{batch}").glob("*.schema.json"))) for batch in range(29, 35))
    templates = sum(len(list((ROOT / "templates" / f"batch{batch}").glob("*.json"))) for batch in range(29, 35))
    assert schemas == 38, schemas
    assert templates == 52, templates
    migrations = list((ROOT / "modules" / "persistence" / "src" / "main" / "resources" / "db" / "migration").glob("V*.sql"))
    assert len(migrations) == 41
    assert (ROOT / "modules" / "product-roadmap-governance" / "pom.xml").is_file()
    assert (ROOT / "modules" / "migration-pack-certification" / "pom.xml").is_file()
    print(json.dumps({
        "new_skills_validated": len(records), "runtime_skills": 615,
        "migration_pack_schemas": schemas, "migration_pack_templates": templates,
        "flyway_migrations": 41, "external_certification_evidence": "NOT_RUN",
    }, indent=2))


if __name__ == "__main__":
    main()
