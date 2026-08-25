#!/usr/bin/env python3
"""List Elmos skills and installation profiles."""

from __future__ import annotations

import argparse
from pathlib import Path
import yaml


def parse_frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="Only show skills in a profile")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = yaml.safe_load((root / "skillpack.yaml").read_text(encoding="utf-8"))
    selected = None
    if args.profile:
        if args.profile not in manifest["profiles"]:
            parser.error(f"Unknown profile: {args.profile}")
        selected = set(manifest["profiles"][args.profile])
    rows = []
    for d in sorted((root / "skills").iterdir()):
        if not (d / "SKILL.md").is_file():
            continue
        fm = parse_frontmatter(d / "SKILL.md")
        if selected is not None and fm["name"] not in selected:
            continue
        rows.append((d.name.split("-", 1)[0], fm["name"], fm["metadata"]["title_zh"], fm["metadata"]["category"], fm["metadata"]["batch"]))
    widths = [max(len(str(row[i])) for row in rows + [("#", "NAME", "TITLE", "CATEGORY", "BATCH")]) for i in range(5)]
    header = ("#", "NAME", "TITLE", "CATEGORY", "BATCH")
    print("  ".join(str(header[i]).ljust(widths[i]) for i in range(5)))
    print("  ".join("-" * widths[i] for i in range(5)))
    for row in rows:
        print("  ".join(str(row[i]).ljust(widths[i]) for i in range(5)))
    print(f"\n{len(rows)} skill(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
