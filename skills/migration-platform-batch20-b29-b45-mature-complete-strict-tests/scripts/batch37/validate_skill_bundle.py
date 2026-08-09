#!/usr/bin/env python3
from __future__ import annotations
import re,sys
from pathlib import Path

def main():
 root=Path(sys.argv[1] if len(sys.argv)>1 else '.agents/skills'); files=sorted(root.glob('b37-*/SKILL.md')); errors=[]; names=[]
 if len(files)!=36: errors.append(f'expected 36 Batch 37 skills, found {len(files)}')
 for p in files:
  text=p.read_text(); m=re.match(r'---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---',text)
  if not m: errors.append(f'invalid front matter: {p}'); continue
  name,desc=m.groups(); names.append(name)
  if name!=p.parent.name: errors.append(f'name mismatch: {p}')
  if len(desc)<80: errors.append(f'description too short: {name}')
  for h in ['## Workflow','## Verification','## Stop and escalate when','## Definition of done']:
   if h not in text: errors.append(f'{name} missing {h}')
 if len(names)!=len(set(names)): errors.append('duplicate skill names')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 print(f'VALID SKILLS: {len(files)}'); return 0
if __name__=='__main__': raise SystemExit(main())
