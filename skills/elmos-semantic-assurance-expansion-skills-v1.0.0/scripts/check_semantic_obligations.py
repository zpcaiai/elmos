#!/usr/bin/env python3
import json,sys
p=sys.argv[1]; d=json.load(open(p)); bad=[]
for o in d.get('obligations',[]):
    if o.get('criticality')=='critical' and o.get('status') not in ('pass','not-applicable','waived'):
        bad.append((o.get('id'),o.get('status')))
if bad:
    print(json.dumps({'status':'blocked','criticalOpen':bad},indent=2)); raise SystemExit(1)
print(json.dumps({'status':'pass','criticalOpen':[]},indent=2))
