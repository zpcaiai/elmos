#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path

def main()->int:
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.agents/skills'); errors=[]; names={}
    files=sorted(root.glob('*/SKILL.md')); b31=[f for f in files if f.parent.name.startswith('b31-')]
    if not b31: errors.append(f'no Batch 31 skills found under {root}')
    for path in b31:
        text=path.read_text(); m=re.match(r'^---\n(.*?)\n---\n',text,re.S)
        if not m: errors.append(f'{path}: missing YAML front matter'); continue
        meta={}
        for line in m.group(1).splitlines():
            if ':' in line:
                k,v=line.split(':',1); meta[k.strip()]=v.strip()
        for k in ['name','description']:
            if not meta.get(k): errors.append(f'{path}: missing {k}')
        name=meta.get('name','')
        if not re.fullmatch(r'[a-z0-9-]{1,64}',name): errors.append(f'{path}: invalid name {name!r}')
        if name in names: errors.append(f'{path}: duplicate name also in {names[name]}')
        names[name]=path
        if len(meta.get('description',''))<50: errors.append(f'{path}: description too vague/short')
        for heading in ['## Workflow','## Verification','## Stop and escalate when','## Definition of done']:
            if heading not in text: errors.append(f'{path}: missing heading {heading}')
    if len(b31)!=22: errors.append(f'expected 22 Batch 31 skills, found {len(b31)}')
    if errors:
        print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
    print(f'OK: {len(b31)} Batch 31 skills'); return 0
if __name__=='__main__': raise SystemExit(main())
