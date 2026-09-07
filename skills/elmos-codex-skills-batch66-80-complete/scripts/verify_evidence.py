#!/usr/bin/env python3
import json,sys
x=json.load(open(sys.argv[1])); req=['schema_version','run_id','skill_id','source_commit','environment','commands','artifacts','state','limitations']; missing=[k for k in req if k not in x]
if missing: print('FAIL missing',missing);raise SystemExit(1)
if x['state']=='certified' and not x.get('certifier',{}).get('independent'): print('FAIL independent certifier required');raise SystemExit(2)
print('PASS evidence structure')
