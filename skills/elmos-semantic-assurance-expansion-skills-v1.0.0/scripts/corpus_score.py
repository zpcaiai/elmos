#!/usr/bin/env python3
import json,sys
r=json.load(open(sys.argv[1])); rows=[]
for x in r.get('routes',[]):
 c=x.get('coverage',{}); score={}
 for k,v in c.items():
  n,d=v.get('numerator',0),v.get('denominator',0); score[k]=None if not d else n/d
 rows.append({'route':x.get('route'),'coverage':score,'status':x.get('status')})
print(json.dumps(rows,indent=2))
