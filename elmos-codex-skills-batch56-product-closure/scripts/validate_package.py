from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'manifest.json').read_text())
errors=[]
names=set()
required=['## Objective','## Scope','## Workflow','## Required Tests','## Verification','## Stop and Escalate','## Definition of Done','## Completion Report']
for s in manifest['skills']:
    p=root/s['path']
    if not p.exists(): errors.append(f'missing {p}') ; continue
    t=p.read_text()
    m=re.search(r'^name:\s*(.+)$',t,re.M)
    if not m or m.group(1).strip()!=s['name']: errors.append(f'name mismatch {p}')
    if s['name'] in names: errors.append(f'duplicate {s["name"]}')
    names.add(s['name'])
    for h in required:
        if h not in t: errors.append(f'{p}: missing {h}')
    if 'BEGIN PRIVATE KEY' in t or re.search(r'(?i)(api[_-]?key|password)\s*[:=]\s*["\'][^"\']{16,}',t): errors.append(f'secret pattern {p}')
if len(manifest['skills'])!=16: errors.append('expected 16 skills')
if errors:
    print('\n'.join(errors)); sys.exit(1)
print('PASS: 16 Batch 56 Skills validated')
