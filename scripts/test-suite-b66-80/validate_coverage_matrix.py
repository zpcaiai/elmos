#!/usr/bin/env python3
import json, sys
cov=json.load(open(sys.argv[1],encoding='utf-8')); cat=json.load(open(sys.argv[2],encoding='utf-8'))
cases={c['case_id']:c for c in cat['cases']}
rows=cov.get('source_skills',[])
if len(rows)!=195: raise SystemExit('ERROR: expected 195 source skills')
nums=[]
for r in rows:
    nums.append(int(r['source_skill_id'][2:]))
    ids=r.get('case_ids',[])
    if len(ids)<2: raise SystemExit(f"ERROR: undercovered {r['source_skill_id']}")
    selected=[cases.get(i) for i in ids]
    if None in selected: raise SystemExit('ERROR: unknown case ref')
    if {c['polarity'] for c in selected} != {'positive','negative'}: raise SystemExit(f"ERROR: missing polarity {r['source_skill_id']}")
    if any(c['source_skill_sha256']!=r['source_skill_sha256'] for c in selected): raise SystemExit('ERROR: source hash mismatch')
if nums!=list(range(223,418)): raise SystemExit('ERROR: source ID continuity')
cross=cov.get('cross_cutting_case_ids',[])
if len(cross)!=60 or any(i not in cases for i in cross): raise SystemExit('ERROR: cross coverage')
print('PASS: PG223-PG417 each has positive and negative coverage; 60 cross cases mapped')
