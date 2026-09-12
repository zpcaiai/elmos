#!/usr/bin/env python3
"""Run only synthetic signed evidence fixtures and a real in-memory SQL example."""
import json, sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/"reference"),str(R)]
from elmos_assurance.core import evaluate
from elmos_assurance.sql_examples import not_in_vs_not_exists
from tests.support import valid_fixture, modify_payload, modify_report, NOW

def run():
    results=[]
    for scenario in ['synthetic-valid','tampered-evidence','missing-audit','mutation-unknown','failed-regression']:
        f=valid_fixture()
        if scenario=='tampered-evidence':modify_payload(f,'regression',lambda p:p.update(expires_at=NOW+500),False)
        if scenario=='missing-audit':f.envelopes=[e for e in f.envelopes if e['payload']['kind']!='audit']
        if scenario=='mutation-unknown':modify_report(f,'mutation',lambda r:r['mutation_checks'].update(unknown=1))
        if scenario=='failed-regression':modify_report(f,'regression',lambda r:r['results'][0].update(status='FAIL'))
        result=evaluate(f.request,f.envelopes,f.blobs,f.context,NOW)
        assert result['production_signing_allowed']is False
        assert (result['verdict']=='PASS')==(scenario=='synthetic-valid')
        results.append({'scenario':scenario,**result})
    a,b=not_in_vs_not_exists([None,1,2],[1]);assert a!=b
    return {'kind':'DEMO_ONLY_NOT_A_CERTIFICATE','real_lean_execution':'NOT_RUN','real_ethen_identity':'UNCONFIGURED','production_signing_allowed':False,'sqlite_counterexample':{'not_in':a,'not_exists':b,'scope':'local SQLite only; no cross-dialect certificate'},'scenarios':results}
if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
