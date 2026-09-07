#!/usr/bin/env python3
"""Generate a compact Markdown task index from docs/task-catalog.json."""
from __future__ import annotations
import argparse
import json
from collections import defaultdict
from pathlib import Path

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("root", nargs="?", default=None)
    p.add_argument("--output", default="docs/TASK-INDEX.md")
    args = p.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "docs/task-catalog.json").read_text(encoding="utf-8"))
    grouped = defaultdict(lambda: defaultdict(list))
    for task in catalog["tasks"]:
        grouped[task["skill"]][task["group"]].append(task)
    lines = ["# Task Index", "", f"Total tasks: **{catalog['task_count']}**", ""]
    for skill, groups in grouped.items():
        lines += [f"## `{skill}`", ""]
        for group, tasks in groups.items():
            lines += [f"### {group}", ""]
            lines += [f"- [ ] `{t['id']}` {t['description']}" for t in tasks]
            lines.append("")
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
