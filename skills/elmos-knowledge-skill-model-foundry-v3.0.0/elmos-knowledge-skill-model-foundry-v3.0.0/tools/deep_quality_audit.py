#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from collections import Counter
import re, yaml
YAML_LOADER=getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
def load_yaml(path): return yaml.load(path.read_text(encoding='utf-8'), Loader=YAML_LOADER)
ROOT=Path(__file__).resolve().parents[1]
skills=[]; priorities=Counter(); evidences=Counter(); statuses=Counter(); cases=Counter(); owners=Counter(); errors=[]
for p in sorted(ROOT.glob('skills/atomic/*/*/skill.yaml')):
    d=load_yaml(p); s=d['spec']; sid=d['metadata']['name']; skills.append(sid)
    priorities[d['metadata']['priority']]+=1; evidences[s['evidence']['minimumLevel']]+=1; statuses[s['maturity']['status']]+=1; owners[d['metadata']['owner']]+=1
    c=load_yaml(p.parent/'evals/cases.yaml')
    for k in ('positive','negative','ambiguous','adversarial'): cases[k]+=len(c.get(k,[]))
for p in ROOT.rglob('*'):
    if not p.is_file() or '__pycache__' in p.parts or p.name=='SHA256SUMS' or p.parent.name=='tools': continue
    if p.stat().st_size==0: errors.append(f'empty: {p.relative_to(ROOT)}')
    if p.suffix in {'.md','.yaml','.yml','.json','.rego','.sql'}:
        text=p.read_text(encoding='utf-8',errors='replace')
        if re.search(r'\b(TBD|TODO|FIXME|PLACEHOLDER|XXX)\b', text): errors.append(f'placeholder: {p.relative_to(ROOT)}')
if errors: raise SystemExit('\n'.join(errors))
print('OK: deep quality audit passed')
print('skills',len(skills),'owners',len(owners),'priorities',dict(priorities),'evidence',dict(evidences),'statuses',dict(statuses),'eval_cases',dict(cases))
