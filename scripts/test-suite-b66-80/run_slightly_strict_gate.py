#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
suite=Path(sys.argv[1]); catalog=json.load(open(suite/'cases/catalog.json',encoding='utf-8'))['cases']
results={p.stem:json.load(open(p,encoding='utf-8')) for p in (suite/'results').glob('*.json')}
counts=Counter(); by_priority={p:Counter() for p in ('P0','P1','P2')}; reasons=[]
waived=0
for c in catalog:
    r=results.get(c['case_id'],{'status':'not-run'}); st=r.get('status','not-run')
    counts[st]+=1; by_priority[c['priority']][st]+=1
    if c['zero_tolerance'] and st!='passed': reasons.append(f"zero-tolerance {c['case_id']} is {st}")
    if st=='waived': waived+=1
def rate(p):
    d=by_priority[p]; denom=sum(d.values()); return (d['passed']/denom) if denom else 1.0
any_run=counts['not-run']<len(catalog)
if not any_run:
    status='NOT_RUN'; reasons=['all cases are not-run']
elif reasons or by_priority['P0']['passed']!=sum(by_priority['P0'].values()):
    status='BLOCKED'
elif rate('P1')>=0.98 and rate('P2')>=0.95:
    status='CONDITIONAL' if waived else 'PASS'
else:
    status='BLOCKED'; reasons.append(f"threshold failure P1={rate('P1'):.4f} P2={rate('P2'):.4f}")
out={'suite_id':'batch66-80-slightly-strict','status':status,'thresholds':{'P0':1.0,'P1':0.98,'P2':0.95,'zero_tolerance_failures':0},'counts':{'overall':dict(counts),'by_priority':{k:dict(v) for k,v in by_priority.items()}},'reasons':reasons[:200],'generated_at':datetime.now(timezone.utc).isoformat()}
json.dump(out,open(suite/'release-gate.json','w',encoding='utf-8'),ensure_ascii=False,indent=2); print(json.dumps(out,ensure_ascii=False,indent=2))
raise SystemExit(0 if status in {'PASS','CONDITIONAL'} else 2)
