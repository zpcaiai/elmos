#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from pathlib import Path

def main() -> int:
    root=Path(sys.argv[1] if len(sys.argv)>1 else '.agents/skills')
    errors=[]; names={}
    files=sorted(root.glob('b29-*/SKILL.md'))
    if not files: errors.append(f'no Batch 29 skills found under {root}')
    for f in files:
        text=f.read_text()
        m=re.match(r'^---\n(.*?)\n---\n',text,re.S)
        if not m: errors.append(f'{f}: missing YAML front matter'); continue
        meta={}
        for line in m.group(1).splitlines():
            if ':' in line:
                k,v=line.split(':',1); meta[k.strip()]=v.strip()
        for k in ['name','description']:
            if not meta.get(k): errors.append(f'{f}: missing {k}')
        name=meta.get('name','')
        if not re.fullmatch(r'[a-z0-9-]{1,64}',name): errors.append(f'{f}: invalid name {name!r}')
        if name in names: errors.append(f'{f}: duplicate name also in {names[name]}')
        names[name]=f
        if len(meta.get('description',''))<40: errors.append(f'{f}: description too vague/short')
        for heading in ['## Workflow','## Verification','## Stop and escalate when','## Definition of done']:
            if heading not in text: errors.append(f'{f}: missing heading {heading}')
    if errors:
        print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
    print(f'OK: {len(files)} skills')
    return 0
if __name__=='__main__': raise SystemExit(main())
