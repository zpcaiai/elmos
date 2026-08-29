#!/usr/bin/env python3
'''Generate a new atomic skill skeleton. Review and register it manually.'''
import argparse, re
from pathlib import Path

ap=argparse.ArgumentParser()
ap.add_argument('pack')
ap.add_argument('name')
ap.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
args=ap.parse_args()
if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', args.name) or len(args.name)>64:
    raise SystemExit('invalid Agent Skills name')
root=Path(args.root)
d=root/'skills/atomic'/args.pack/args.name
d.mkdir(parents=True, exist_ok=False)
content=("---\n"
         f"name: {args.name}\n"
         "description: Use this skill when...\n"
         "---\n\n"
         f"# {args.name}\n\n"
         "## Goal\n\nTBD\n")
(d/'SKILL.md').write_text(content, encoding='utf-8')
print(d)
