#!/usr/bin/env python3
"""Validate static package content, DAG, schemas, policy and distribution hashes.
Does not execute untrusted code, create a sandbox or grant deployment qualification.
"""
from __future__ import annotations
import argparse,hashlib,json,re,sys
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
R=Path(__file__).resolve().parents[1]

def static_files():
    return sorted(p for p in R.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and 'reports' not in p.relative_to(R).parts and p.name not in {'FILES.sha256','VALIDATION_REPORT.md','VALIDATION_REPORT.json'})
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def validate(skip_integrity=False):
    manifest=load(R/'manifest.json');errors=[]
    assert manifest['name']=='elmos-live-workbench' and manifest['version']=='1.0.0'
    skills=manifest['skills'];by={s['name']:s for s in skills}
    assert len(skills)==len(by)==28 and manifest['external_router_count']==1
    contracts={};case_ids=set()
    for s in skills:
        base=R/s['path'];raw=(base/'SKILL.md').read_text()
        front=yaml.safe_load(raw.split('---',2)[1])
        assert front['name']==s['name'] and front['description']
        assert len(raw.splitlines())<500
        assert len(s['name'])<=64 and re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',s['name'])
        c=load(base/'compiled-contract.json');contracts[s['name']]=c
        assert c['name']==s['name'] and c['priority']==s['priority']
        assert c['status']=='implementation-required' and c['may_self_certify_e5'] is False
        for dep in c['dependencies']:assert dep in by,dep
        for ref in c['contract_refs']+c['hard_policies']:assert (R/ref).is_file(),ref
        cases=load(base/'evals/cases.json')
        # Case list is versioned per workflow in the source package.
        entries=cases if isinstance(cases,list) else cases['cases']
        assert len(entries)==3
        for ac in c['acceptance_cases']:
            assert ac not in case_ids;case_ids.add(ac)
    visited=set();active=set()
    def visit(name):
        assert name not in active,'DAG cycle at '+name
        if name in visited:return
        active.add(name)
        for dep in contracts[name]['dependencies']:visit(dep)
        active.remove(name);visited.add(name)
    for name in by:visit(name)
    # Batch position must never schedule a dependency in a later batch.
    batches=load(R/'workflows/implementation-batches.json')['batches']
    schedule={name:i for i,b in enumerate(batches) for name in b['skills']}
    assert set(schedule)==set(by)
    assert sum(len(b['skills']) for b in batches)==len(by)
    for name,c in contracts.items():
        for dep in c['dependencies']:assert schedule[dep]<=schedule[name],f'{name} scheduled before {dep}'
    schemas={p.name:load(p) for p in (R/'contracts').glob('*.schema.json')}
    assert len(schemas)==12
    for schema in schemas.values():Draft202012Validator.check_schema(schema)
    for p in (R/'examples').glob('*.json'):Draft202012Validator(schemas[p.stem+'.schema.json']).validate(load(p))
    candidates=list((R/'adapters/candidates').glob('*.json'))
    for p in candidates:
        profile=load(p);Draft202012Validator(schemas['runtime-profile.schema.json']).validate(profile)
        assert profile['qualification_status']=='candidate' and not profile['evidence_ids']
    policy=load(R/'policies/preview-window.json')
    assert policy['preview_seconds']==600 and policy['build_time_counts_as_preview'] is False
    assert all(policy[k] is False for k in ['extension_by_refresh','pause_freezes_timer','same_session_ready_resets_timer','same_session_restart_resets_timer'])
    for name in ['README.md','INTEGRATION.md','DESIGN.zh-CN.md','IMPLEMENTATION_PLAN.md','contracts/host-ports.ts','evals/qualification-plan.json','provenance/sources.json']:assert (R/name).is_file(),name
    if not skip_integrity and (R/'FILES.sha256').exists():
        expected={}
        for line in (R/'FILES.sha256').read_text().splitlines():
            sha,rel=line.split('  ',1);expected[rel]=sha
        actual={str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in static_files()}
        assert expected==actual,'distribution static file hash mismatch; rerun with --skip-integrity only for intentional edits'
    return {'status':'passed','internal_workflows':len(skills),'workflow_acceptance_cases':len(case_ids),'json_schemas':len(schemas),'runtime_candidates':len(candidates),'examples':len(list((R/'examples').glob('*.json'))),'dependency_dag':'acyclic','batch_dependencies':'valid','scope':'static-package-validation-only'}
if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--skip-integrity',action='store_true');args=a.parse_args()
    try:result=validate(args.skip_integrity)
    except Exception as e:
        print(json.dumps({'status':'failed','error':type(e).__name__+': '+str(e)},ensure_ascii=False));sys.exit(1)
    print(json.dumps(result,ensure_ascii=False,indent=2))
