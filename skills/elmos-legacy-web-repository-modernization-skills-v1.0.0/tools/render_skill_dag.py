#!/usr/bin/env python3
from pathlib import Path
from collections import defaultdict
import yaml

root = Path(__file__).resolve().parents[1]
pkg = yaml.safe_load((root / "package.yaml").read_text(encoding="utf-8"))
skills = pkg["skills"]
groups = defaultdict(list)
for s in skills:
    groups[s["phase"]].append(s)

lines = ["flowchart TD"]
for phase, items in groups.items():
    lines.append(f'  subgraph {phase.replace("-", "_")}["{phase}"]')
    for s in items:
        lines.append(f'    {s["id"].replace("-", "_")}["{s["id"]}"]')
    lines.append("  end")
for s in skills:
    for dep in s.get("requires", []):
        lines.append(f'  {dep.replace("-", "_")} --> {s["id"].replace("-", "_")}')
out = root / "build" / "skill-dag.mmd"
out.parent.mkdir(exist_ok=True)
out.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(out)
