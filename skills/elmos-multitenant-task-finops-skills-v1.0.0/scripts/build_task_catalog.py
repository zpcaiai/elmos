#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    manifest = json.loads((ROOT / "skill-manifest.json").read_text(encoding="utf-8"))
    skills = {item["id"]: item for item in manifest["skills"]}
    with (ROOT / "docs" / "TASK-MATRIX.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    catalog = {
        "schema_version": "1.0",
        "package": manifest["package"],
        "version": manifest["version"],
        "total_tasks": len(rows),
        "tasks": [],
    }
    for row in rows:
        skill = skills[row["skill_id"]]
        catalog["tasks"].append({
            "task_id": row["task_id"],
            "skill_id": row["skill_id"],
            "skill_name": row["skill_name"],
            "task": row["task"],
            "priority": row["priority"],
            "gate": row["gate"],
            "evidence_required": row["evidence_required"].lower() == "true",
            "skill_path": skill["path"],
            "depends_on": skill.get("depends_on", []),
        })
    output = ROOT / "docs" / "task-catalog.json"
    output.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {output.relative_to(ROOT)} with {len(rows)} tasks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
