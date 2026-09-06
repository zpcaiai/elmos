#!/usr/bin/env python3
"""Fail-closed completeness gate. Evidence authenticity is checked by the real host,
not by this file-list/status model. A passed result is NOT E5 certification.
"""
import argparse,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def check(report,policy):
    failures=[]
    if report.get('scope')!=policy['scope']:failures.append('scope mismatch')
    rows=report.get('results',[])
    names=[x.get('surface') for x in rows]
    if len(names)!=len(set(names)):failures.append('duplicate surface')
    by={x.get('surface'):x for x in rows}
    for name in policy['required_surfaces']:
        x=by.get(name)
        if not x or x.get('status')!='passed' or not x.get('evidence_paths'):
            failures.append('missing, not passed or no evidence: '+name)
    if report.get('may_self_certify_e5') is not False:failures.append('certification authority invalid')
    return failures
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('report',type=Path);args=p.parse_args()
    try:failures=check(json.loads(args.report.read_text()),json.loads((R/'policies/release-gates.json').read_text()))
    except (OSError,ValueError,KeyError) as e:failures=[str(e)]
    print(json.dumps({'release':'BLOCKED' if failures else 'COMPLETENESS_PASSED_HOST_AUTHENTICITY_REQUIRED','failures':failures,'e5_certificate':False},ensure_ascii=False,indent=2))
    sys.exit(1 if failures else 0)
