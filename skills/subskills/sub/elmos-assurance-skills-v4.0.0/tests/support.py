"""Locally generated simulation evidence, not reports of native product tests."""
from __future__ import annotations
import base64
from dataclasses import dataclass, replace
from typing import Any, Callable
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from elmos_assurance.core import (
    TrustedContext, TrustedKey, digest, canonical, bytes_digest,
    signing_message, evidence_basis, strict_loads,
)
NOW = 1_788_942_600
KINDS = ['build','contract','smoke','regression','differential','mutation','proof','audit']


@dataclass
class Fixture:
    request: dict
    envelopes: list[dict]
    blobs: dict[str, bytes]
    context: TrustedContext
    private_keys: dict[str, Ed25519PrivateKey]


def sign(key_id: str, payload: dict, keys: dict[str, Ed25519PrivateKey]) -> dict:
    signature = keys[key_id].sign(signing_message(key_id, payload))
    return {'format':'elmos-demo-envelope-v1','key_id':key_id,'payload':payload,
            'signature':base64.b64encode(signature).decode('ascii')}


def valid_fixture() -> Fixture:
    keys = {'demo-runner': Ed25519PrivateKey.generate(), 'demo-ethen': Ed25519PrivateKey.generate()}
    req = {'schema_version':'4.0','tenant_id':'demo-tenant','project_id':'demo-project',
           'run_id':'demo-run','profile_id':'elmos.assurance/v4/reference-strict',
           'target_level':'E5','builder_control_domain':'demo-builder',
           'revision_set':{k:digest('SYNTHETIC-'+k) for k in ['source','target','artifact','scope','contract','policy','environment','toolchain','suite','data','comparator','rules']},
           'obligations':[{'id':'o-'+k,'kind':k,'critical':True,'case_ids':['c-'+k]} for k in KINDS]}
    blobs: dict[str,bytes]={}
    envelopes=[]
    for kind in KINDS:
        report={'schema_version':'4.0','kind':kind,'results':[{'obligation_id':'o-'+kind,'case_id':'c-'+kind,'status':'PASS','assertions':1}],'findings':[]}
        if kind=='mutation':
            report['mutation_checks']={'killed':10,'survived':0,'unknown':0,'invalid':0,'equivalent':0,'must_kill_survived':0,'exclusions_reviewed':True}
        if kind=='proof':
            report['proof_checks']={k:True for k in ['statement_matches','axioms_approved','artifact_binding_verified','preconditions_verified','independent_checker_verified']}
        if kind=='audit':
            report['audit_checks']={'basis_digest':evidence_basis(envelopes),'independence_reviewed':True,'discovery_diff_count':0,'challenge_count':3,'challenge_passed':3}
        raw=canonical(report); h=bytes_digest(raw);blobs[h]=raw
        payload={'schema_version':'4.0','evidence_id':'e-'+kind,'tenant_id':req['tenant_id'],'project_id':req['project_id'],'run_id':req['run_id'],
                 'request_digest':digest(req),'kind':kind,'obligation_ids':['o-'+kind],'status':'PASS','issued_at':NOW-10,'expires_at':NOW+100,'report_digest':h}
        key_id='demo-ethen' if kind=='audit' else 'demo-runner'
        envelopes.append(sign(key_id,payload,keys))
    trust={
        'demo-runner':TrustedKey(keys['demo-runner'].public_key(),'demo-builder',frozenset(KINDS[:-1]),frozenset({'demo-tenant'})),
        'demo-ethen':TrustedKey(keys['demo-ethen'].public_key(),'demo-auditor',frozenset({'audit'}),frozenset({'demo-tenant'})),
    }
    ctx=TrustedContext(trust,digest(req),frozenset(e['payload']['evidence_id'] for e in envelopes),'demo-builder',frozenset({'demo-auditor'}))
    return Fixture(req,envelopes,blobs,ctx,keys)


def modify_payload(f:Fixture,kind:str,change:Callable[[dict],None],resign=True)->None:
    e=next(e for e in f.envelopes if e['payload']['kind']==kind)
    change(e['payload'])
    if resign:
        e.update(sign(e['key_id'],e['payload'],f.private_keys))


def modify_report(f:Fixture,kind:str,change:Callable[[dict],None],refresh_audit=True)->None:
    e=next(e for e in f.envelopes if e['payload']['kind']==kind)
    report=strict_loads(f.blobs[e['payload']['report_digest']]); change(report)
    raw=canonical(report); h=bytes_digest(raw); f.blobs[h]=raw
    e['payload']['report_digest']=h
    e.update(sign(e['key_id'],e['payload'],f.private_keys))
    if refresh_audit and kind!='audit':
        modify_report(f,'audit',lambda r:r['audit_checks'].update(basis_digest=evidence_basis(f.envelopes)),False)
