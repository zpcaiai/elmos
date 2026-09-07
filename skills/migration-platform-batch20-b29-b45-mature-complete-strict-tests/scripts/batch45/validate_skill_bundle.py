#!/usr/bin/env python3
from pathlib import Path
import re,sys,json
CFG=json.loads(Path(__file__).with_name('config.json').read_text())
root=Path(sys.argv[1] if len(sys.argv)>1 else '.')
files=[]
for n in CFG['SKILL_NAMES']:
 p=root/'.agents/skills'/n/'SKILL.md'
 if not p.is_file(): print('missing '+str(p),file=sys.stderr); raise SystemExit(2)
 txt=p.read_text()
 for token in ['name: '+n,'## Workflow','## Verification','## Stop and escalate when','## Definition of done']:
  if token not in txt: print(f'{p} missing {token}',file=sys.stderr); raise SystemExit(2)
 files.append(p)
print(f"SKILL BUNDLE VALID: {len(files)}")
