#!/usr/bin/env python3
from pathlib import Path
import json, sys
root=Path(__file__).resolve().parents[1]
errors=[]
required=['README.md','package.yaml','docs/ARCHITECTURE.md','docs/INVARIANTS.md','implementation/work-packages.yaml']
for r in required:
    if not (root/r).exists(): errors.append(f'missing {r}')
for p in (root/'contracts/schemas').glob('*.json'):
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'{p}: {e}')
for p in (root/'contracts/examples').glob('*.json'):
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'{p}: {e}')
# skills have five-file contracts
for d in (root/'skills').iterdir():
    if d.is_dir():
        for f in ['SKILL.md','manifest.yaml','acceptance.yaml','implementation.yaml','runbook.md']:
            if not (d/f).exists(): errors.append(f'{d.name}: missing {f}')
if errors:
    print('FAIL')
    for e in errors: print(e)
    sys.exit(1)
print('PASS')
print('schemas',len(list((root/'contracts/schemas').glob('*.json'))))
print('skills',len([d for d in (root/'skills').iterdir() if d.is_dir()]))
