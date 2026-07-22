#!/usr/bin/env python3
from __future__ import annotations
import re,sys
from pathlib import Path
EXPECTED=18
def main():
 root=Path(sys.argv[1] if len(sys.argv)>1 else '.agents/skills'); errors=[]; names={}; batch=sorted(p for p in root.glob('b36-*/SKILL.md'))
 if not batch: errors.append(f'no Batch 36 skills found under {root}')
 for path in batch:
  text=path.read_text(); m=re.match(r'^---\n(.*?)\n---\n',text,re.S)
  if not m: errors.append(f'{path}: missing YAML front matter'); continue
  meta={}
  for line in m.group(1).splitlines():
   if ':' in line: k,v=line.split(':',1); meta[k.strip()]=v.strip()
  for key in ('name','description'):
   if not meta.get(key): errors.append(f'{path}: missing {key}')
  name=meta.get('name','')
  if not re.fullmatch(r'[a-z0-9-]{1,64}',name): errors.append(f'{path}: invalid name {name!r}')
  if name in names: errors.append(f'{path}: duplicate name also in {names[name]}')
  names[name]=path
  if len(meta.get('description',''))<50: errors.append(f'{path}: description too vague/short')
  for h in ('## Workflow','## Verification','## Stop and escalate when','## Definition of done'):
   if h not in text: errors.append(f'{path}: missing heading {h}')
 if len(batch)!=EXPECTED: errors.append(f'expected {EXPECTED} Batch 36 skills, found {len(batch)}')
 if errors:
  print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
 print(f'OK: {len(batch)} Batch 36 skills'); return 0
if __name__=='__main__': raise SystemExit(main())
