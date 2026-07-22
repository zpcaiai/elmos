#!/usr/bin/env python3
import csv, hashlib, json, re, sys, zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
errors=[]
manifest=json.loads((root/'manifest.json').read_text())
cases=json.loads((root/'CASE_CATALOG.json').read_text())['cases']
skills=list((root/'agent-skills/runtime').glob('*/SKILL.md'))
if len(skills)!=88: errors.append(f'expected 88 Skill files, got {len(skills)}')
if len(cases)!=750: errors.append(f'expected 750 cases, got {len(cases)}')
ids=[]
headings=['## 1. Objective','## 2. Target Scope','## 3. Strictness Profile','## 4. Inputs','## 5. Required Fixtures','## 6. Preconditions','## 7. Test Cases','## 8. Deterministic Oracles','## 9. Execution Procedure','## 10. Failure Injection','## 11. Security and Tenant Isolation','## 12. Replay and Idempotency','## 13. Evidence Contract','## 14. Anti-Fraud Rules','## 15. Reporting','## 16. Acceptance Criteria','## 17. Release Impact','## 18. Definition of Done']
for p in skills:
 t=p.read_text()
 m=re.search(r'^test_skill_id:\s*(T\d{3})$',t,re.M)
 if not m: errors.append(f'missing test_skill_id: {p}')
 else: ids.append(m.group(1))
 for h in headings:
  if h not in t: errors.append(f'missing {h}: {p}')
 if 'TODO' in t: errors.append(f'TODO placeholder: {p}')
if sorted(ids)!=[f'T{i:03d}' for i in range(1,89)]: errors.append('test Skill IDs are not exactly T001-T088')
caseids=[c['case_id'] for c in cases]
if len(caseids)!=len(set(caseids)): errors.append('duplicate case IDs')
if set(c['test_skill_id'] for c in cases)!=set(ids): errors.append('case/test Skill reference mismatch')
with (root/'COVERAGE_MATRIX.csv').open() as f: rows=list(csv.DictReader(f))
if len(rows)!=1296: errors.append(f'expected 1296 coverage rows, got {len(rows)}')
if set(int(r['source_batch']) for r in rows)!=set(range(1,66)): errors.append('batch coverage is not 1-65')
if any(not r['direct_test_skill_id'] for r in rows): errors.append('source Skill missing direct test coverage')
for f in (root/'schemas').glob('*.json'): json.loads(f.read_text())
for f in (root/'examples').glob('*.json'): json.loads(f.read_text())
status='PASSED' if not errors else 'FAILED'
report={'status':status,'testSkillCount':len(skills),'caseCount':len(cases),'sourceSkillCoverage':len(rows),'batchCoverage':'1-65','errors':errors}
(root/'VALIDATION_REPORT.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
sys.exit(0 if not errors else 1)
