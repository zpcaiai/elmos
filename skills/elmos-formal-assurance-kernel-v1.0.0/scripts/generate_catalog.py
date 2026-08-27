#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    package = yaml.safe_load((ROOT / "PACKAGE_MANIFEST.yaml").read_text(encoding="utf-8"))
    rows = []
    registry = []
    for manifest_path in sorted(ROOT.glob("skills/P*/*/manifest.yaml")):
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        meta = manifest["metadata"]
        skill_dir = manifest_path.parent
        rel = skill_dir.relative_to(ROOT)
        rows.append({
            "name":meta["name"],"title":meta["title"],"priority":meta["priority"],
            "domain":meta["domain"],"path":f"{rel.as_posix()}/SKILL.md",
            "dependencies":manifest["spec"].get("dependencies",[])
        })
        registry.append({
            "id":meta["name"],"title":meta["title"],"priority":meta["priority"],
            "domain":meta["domain"],"manifest":manifest_path.relative_to(ROOT).as_posix()
        })

    index = {
        "apiVersion":"elmos.ai/v2alpha1","kind":"SkillIndex",
        "metadata":{"packageId":package["metadata"]["packageId"],
                    "generatedAt":package["metadata"]["releaseDate"] + "T00:00:00Z"},
        "spec":{"skills":rows},
    }
    (ROOT / "skills/index.yaml").write_text(
        yaml.safe_dump(index,sort_keys=False,allow_unicode=True,width=110),encoding="utf-8"
    )
    (ROOT / "skills/registry.generated.json").write_text(
        json.dumps({"packageId":package["metadata"]["packageId"],"skills":registry},
                   ensure_ascii=False,indent=2) + "\n",encoding="utf-8"
    )

    lines = [
        "# Elmos Formal Assurance Skills Index","",
        f"Package: `{package['metadata']['packageId']}`","",
        "| # | Priority | Domain | Skill | Title |",
        "|---:|---|---|---|---|",
    ]
    for i,row in enumerate(rows,1):
        lines.append(f"| {i} | {row['priority']} | {row['domain']} | "
                     f"[`{row['name']}`]({row['path']}) | {row['title']} |")
    lines += ["","## Counts",""]
    by_priority = {}
    by_domain = {}
    for row in rows:
        by_priority[row["priority"]] = by_priority.get(row["priority"],0) + 1
        by_domain[row["domain"]] = by_domain.get(row["domain"],0) + 1
    lines.append("- Priority: " + ", ".join(f"{k}={v}" for k,v in sorted(by_priority.items())))
    lines.append("- Domain: " + ", ".join(f"{k}={v}" for k,v in sorted(by_domain.items())))
    (ROOT / "SKILLS_INDEX.md").write_text("\n".join(lines) + "\n",encoding="utf-8")
    print(f"generated catalog for {len(rows)} skills")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
