#!/usr/bin/env python3
from __future__ import annotations
import json, re, sys
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
errors=[]
manifest=yaml.safe_load((ROOT/'manifest.yaml').read_text())
catalog=yaml.safe_load((ROOT/'registry/skill-catalog.yaml').read_text())
items=catalog['spec']['skills']
ids=set()
for item in items:
    sid=item['id']
    if sid in ids: errors.append(f'duplicate id: {sid}')
    ids.add(sid)
    if len(sid)>64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', sid): errors.append(f'invalid id: {sid}')
    p=ROOT/item['path']
    if not p.exists(): errors.append(f'missing SKILL.md: {p}')
    y=p.parent/'skill.yaml'
    if not y.exists(): errors.append(f'missing skill.yaml: {y}')
    else:
        obj=yaml.safe_load(y.read_text())
        if obj['metadata']['name'] != sid: errors.append(f'name mismatch: {sid}')
        gates=obj['spec'].get('evidence',{}).get('requiredGates',[])
        if not gates: errors.append(f'no evidence gates: {sid}')
        if not obj['spec'].get('rollback',{}).get('required'): errors.append(f'rollback not required: {sid}')
    text=p.read_text()
    m=re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m: errors.append(f'frontmatter missing: {sid}')
    else:
        fm=yaml.safe_load(m.group(1))
        if fm.get('name') != sid: errors.append(f'frontmatter name mismatch: {sid}')
        if len(fm.get('description',''))>1024: errors.append(f'description too long: {sid}')
count=manifest['metadata']['atomicSkillCount']
if count != len(items): errors.append(f'count mismatch manifest={count} catalog={len(items)}')
if errors:
    print('\n'.join('ERROR '+x for x in errors))
    sys.exit(1)
print(f'OK: {len(items)} atomic skills, {manifest["metadata"]["metaSkillCount"]} meta skills')
