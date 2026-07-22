from pathlib import Path
import json,re,sys
root=Path(__file__).resolve().parents[1]
files=sorted((root/'skills').rglob('SKILL.md'))
errs=[]
if len(files)!=180: errs.append(f'expected 180 skills, found {len(files)}')
ids=[]
heads=['## 1. Objective','## 3. Inputs','## 4. Outputs','## 6. Workflow','## 12. Evidence Contract','## 14. Unit Tests','## 15. Integration Tests','## 16. Negative Tests','## 17. Acceptance Criteria','## 18. Definition of Done']
for p in files:
    t=p.read_text(encoding='utf-8')
    m=re.search(r'^id:\s*(PG\d+)',t,re.M)
    if not m: errs.append(f'missing id: {p}'); continue
    ids.append(m.group(1))
    for h in heads:
        if h not in t: errs.append(f'missing {h}: {p}')
    if 'TODO' in t or 'TBD' in t: errs.append(f'placeholder: {p}')
expected=[f'PG{i:03d}' for i in range(223,403)]
if ids!=expected: errs.append('skill id sequence mismatch')
for p in list((root/'schemas').glob('*.json'))+list((root/'examples').glob('*.json')):
    try: json.loads(p.read_text(encoding='utf-8'))
    except Exception as e: errs.append(f'invalid json {p}: {e}')
if errs:
    print('VALIDATION FAILED')
    print('\n'.join(errs))
    sys.exit(1)
print(json.dumps({'status':'PASSED','skills':len(files),'first_id':ids[0],'last_id':ids[-1],'schemas':len(list((root/'schemas').glob('*.json'))),'examples':len(list((root/'examples').glob('*.json')))},indent=2))
