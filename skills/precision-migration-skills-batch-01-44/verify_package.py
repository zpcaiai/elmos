#!/usr/bin/env python3
from pathlib import Path
import json, re, hashlib, sys
ROOT=Path(__file__).resolve().parent
errors=[]
batches=sorted((ROOT/'batches').glob('batch-*'))
if len(batches)!=44: errors.append(f'expected 44 batches, got {len(batches)}')
names=[]
required=['## Purpose','## Inputs','## Outputs','## Workflow','## Validation gates','## Evidence artifacts','## Failure codes','## Definition of done']
for b in batches:
    if not (b/'SKILL.md').exists(): errors.append(f'missing batch SKILL: {b}')
    for s in sorted((b/'skills').glob('*')):
        p=s/'SKILL.md'
        if not p.exists(): errors.append(f'missing {p}'); continue
        text=p.read_text(encoding='utf-8')
        m=re.match(r'^---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---',text)
        if not m: errors.append(f'bad frontmatter: {p}'); continue
        name=m.group(1).strip(); names.append(name)
        if name!=s.name: errors.append(f'name/path mismatch: {p}')
        for sec in required:
            if sec not in text: errors.append(f'missing {sec} in {p}')
        if 'TODO' in text or 'TBD' in text: errors.append(f'placeholder in {p}')
if len(names)!=len(set(names)): errors.append('duplicate skill names')
expected=587
if len(names)!=587: errors.append(f'expected 587 skills, got {len(names)}')
manifest=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8')) if (ROOT/'manifest.json').exists() else None
if manifest:
    for item in manifest['files']:
        p=ROOT/item['path']
        if not p.exists(): errors.append(f'manifest missing: {p}'); continue
        digest=hashlib.sha256(p.read_bytes()).hexdigest()
        if digest!=item['sha256']: errors.append(f'hash mismatch: {p}')
print(json.dumps({'ok':not errors,'batch_count':len(batches),'skill_count':len(names),'errors':errors},ensure_ascii=False,indent=2))
sys.exit(1 if errors else 0)
