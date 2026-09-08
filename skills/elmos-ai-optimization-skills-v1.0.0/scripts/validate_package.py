#!/usr/bin/env python3
import argparse,ast,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def readjson(p):return json.loads(p.read_text(),parse_constant=lambda v:(_ for _ in ()).throw(ValueError('nonfinite '+v)))
def validate(root,check_hashes=True):
    try:
        import yaml
        from jsonschema import Draft202012Validator
        m=yaml.safe_load((root/'manifest.yaml').read_text());assert m['new_elmos_routes']==0 and m['codex_discoverable_skills']==1 and m['production_qualified'] is False
        skills=list(root.rglob('SKILL.md'));assert len(skills)==1
        fm=yaml.safe_load(skills[0].read_text().split('---',2)[1]);assert fm['name']=='elmos-ai-optimization' and fm['description']
        workflows=list((root/'references/workflows').glob('*.md'));assert len(workflows)==3
        tasks=yaml.safe_load((root/'tasks/tasks.yaml').read_text())['tasks'];cases=yaml.safe_load((root/'acceptance.yaml').read_text())['cases'];ids={t['id'] for t in tasks};ac={c['id'] for c in cases}
        assert len(ids)==len(tasks) and len(ac)==len(cases)
        deps={t['id']:t['depends_on'] for t in tasks};done=set();active=set()
        def visit(n):
            if n not in ids or n in active:raise ValueError('DAG missing/cycle')
            if n in done:return
            active.add(n)
            for d in deps[n]:visit(d)
            active.remove(n);done.add(n)
        for t in tasks:visit(t['id']);assert set(t['acceptance_ids'])<=ac and t['status']=='not_started'
        for c in cases:assert c['task'] in ids and c['host_status']=='not_run'
        ss=list((root/'contracts/schemas').glob('*.json'))
        for p in ss:Draft202012Validator.check_schema(readjson(p))
        examples=readjson(root/'contracts/examples/index.json')
        for e in examples:Draft202012Validator(readjson(root/e['schema'])).validate(readjson(root/e['example']))
        for p in root.rglob('*.py'):ast.parse(p.read_text(),filename=str(p))
        for p in root.rglob('*'):
            if p.is_symlink():raise ValueError('symlink in package')
        for name in ['manifest.yaml','implementation.yaml','acceptance.yaml','runbook.md','SPEC.md','INTEGRATION.md','IMPLEMENTATION_PLAN.md','CODEX_START_PROMPT.md','reports/qualification.json']:assert(root/name).is_file()
        if check_hashes:
            sys.path.insert(0,str(root/'scripts'));from install import manifest;manifest(root)
        return dict(status='pass',codex_skills=len(skills),internal_workflows=len(workflows),tasks=len(tasks),host_acceptance_definitions=len(cases),schemas=len(ss),schema_valid_examples=len(examples),host_integration_verified=False,production_qualified=False)
    except Exception as e:return dict(status='failed',error=type(e).__name__+': '+str(e),production_qualified=False)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--skip-hashes',action='store_true');a=p.parse_args();r=validate(ROOT,not a.skip_hashes);print(json.dumps(r,ensure_ascii=False,indent=2));sys.exit(0 if r['status']=='pass' else 1)
