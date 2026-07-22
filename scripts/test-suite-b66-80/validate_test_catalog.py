#!/usr/bin/env python3
import json, sys
from collections import Counter
p=sys.argv[1]
data=json.load(open(p,encoding='utf-8')); cases=data.get('cases',[])
if data.get('case_count')!=450 or len(cases)!=450: raise SystemExit('ERROR: expected 450 cases')
ids=[c.get('case_id') for c in cases]
if len(set(ids))!=len(ids): raise SystemExit('ERROR: duplicate case id')
required={'case_id','batch','owner_test_skill','title','priority','category','polarity','given','when','then','oracle','evidence_required','zero_tolerance','required_real_system','replayable','status'}
for c in cases:
    miss=required-set(c)
    if miss: raise SystemExit(f"ERROR: {c.get('case_id')} missing {sorted(miss)}")
    if c['priority'] not in {'P0','P1','P2'}: raise SystemExit('ERROR: bad priority')
    if c['status']!='not-run': raise SystemExit('ERROR: catalog must be not-run')
    if len(c['evidence_required'])<3 or not c['oracle'].get('independence_required'): raise SystemExit('ERROR: weak evidence/oracle')
source=[c for c in cases if c['source_skill_id']]
cross=[c for c in cases if not c['source_skill_id']]
if len(source)!=390 or len(cross)!=60: raise SystemExit('ERROR: expected 390 source and 60 cross cases')
pol=Counter(c['polarity'] for c in source)
if pol!={'positive':195,'negative':195}: raise SystemExit(f'ERROR: polarity counts {pol}')
print('PASS: 450 cases validated; 390 source-specific + 60 cross-cutting')
