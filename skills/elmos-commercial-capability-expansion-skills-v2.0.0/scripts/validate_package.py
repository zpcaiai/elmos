#!/usr/bin/env python3
from pathlib import Path
import json, re, sys
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'manifest.json').read_text())
errors=[]
seen=set()
for s in manifest['skills']:
    if s['id'] in seen: errors.append(f"duplicate id: {s['id']}")
    seen.add(s['id'])
    p=root/s['path']
    if not p.exists(): errors.append(f"missing: {p}"); continue
    txt=p.read_text()
    if not txt.startswith('---\n'): errors.append(f"frontmatter missing: {p}")
    if f"name: {s['id']}" not in txt: errors.append(f"name mismatch: {p}")
    if len(txt.splitlines())>500: errors.append(f"SKILL.md >500 lines: {p}")
for schema in (root/'schemas').glob('*.json'):
    try: json.loads(schema.read_text())
    except Exception as e: errors.append(f"invalid json {schema}: {e}")
if errors:
    print('\n'.join(errors)); sys.exit(1)
print(f"OK: {len(manifest['skills'])} skills validated")
