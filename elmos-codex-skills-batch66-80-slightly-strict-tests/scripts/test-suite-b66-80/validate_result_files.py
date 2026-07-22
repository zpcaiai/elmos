#!/usr/bin/env python3
import json, sys
from pathlib import Path
suite=Path(sys.argv[1]); cat=json.load(open(suite/'cases/catalog.json',encoding='utf-8'))
expected={c['case_id'] for c in cat['cases']}; paths=list((suite/'results').glob('*.json'))
found={p.stem for p in paths}
if found!=expected: raise SystemExit(f'ERROR: result files mismatch missing={len(expected-found)} extra={len(found-expected)}')
allowed={'not-run','passed','failed','blocked','skipped','waived','flaky'}
for p in paths:
    r=json.load(open(p,encoding='utf-8'))
    if r.get('case_id')!=p.stem or r.get('status') not in allowed: raise SystemExit(f'ERROR: invalid result {p}')
    if r['status']=='passed' and (not r.get('source_sha256') or not r.get('environment_sha256') or len(r.get('evidence',[]))<2):
        raise SystemExit(f'ERROR: passed without evidence {p}')
print(f'PASS: {len(paths)} result files validated')
