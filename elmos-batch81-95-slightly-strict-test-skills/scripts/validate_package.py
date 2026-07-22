#!/usr/bin/env python3
import csv, json, re, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
errors=[]
manifest=json.loads((root/'manifest.json').read_text())
cases=json.loads((root/'CASE_CATALOG.json').read_text())
skills=list((root/'agent-skills'/'runtime').glob('*/SKILL.md'))
if len(skills)!=manifest['test_skill_count']: errors.append(f"skill count {len(skills)}")
if len(cases)!=manifest['case_count']: errors.append(f"case count {len(cases)}")
ids=[]
headings=['## 1. Objective','## 3. Target Skills','## 7. Test Portfolio','## 12. Evidence Contract','## 16. Anti-Fraud Controls','## 18. Definition of Done']
for p in skills:
 t=p.read_text()
 m=re.search(r'^id:\s*(T\d+)',t,re.M)
 if not m: errors.append(f'missing id {p}')
 else: ids.append(m.group(1))
 for h in headings:
  if h not in t: errors.append(f'missing {h} in {p}')
if len(ids)!=len(set(ids)): errors.append('duplicate test skill id')
with (root/'COVERAGE_MATRIX.csv').open(encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
if len(rows)!=180: errors.append(f'coverage rows {len(rows)}')
if len({r['source_skill_id'] for r in rows})!=180: errors.append('source coverage not unique')
case_ids={c['id'] for c in cases}
for r in rows:
 if r['direct_case_id'] not in case_ids: errors.append(f"missing direct case {r['direct_case_id']}")
for p in (root/'schemas').glob('*.json'): json.loads(p.read_text())
print(json.dumps({'status':'PASSED' if not errors else 'FAILED','errors':errors,'skills':len(skills),'cases':len(cases),'coverage':len(rows)},indent=2))
sys.exit(1 if errors else 0)
