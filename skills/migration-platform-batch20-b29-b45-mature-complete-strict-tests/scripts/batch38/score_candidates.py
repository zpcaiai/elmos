#!/usr/bin/env python3
from pathlib import Path
import json,sys
p=Path(sys.argv[1]); obj=json.loads(p.read_text()); rows=obj.get('candidates',[])
for r in rows:
 r['score']=round(sum(float(r.get(k,0)) for k in ['customer_demand','risk_reduction','reuse','readiness','margin'])/5,4)
rows.sort(key=lambda x:x.get('score',0),reverse=True); print(json.dumps(rows,indent=2))
