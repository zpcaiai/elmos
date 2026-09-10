#!/usr/bin/env python3
"""Offline structural validator. Does not execute a native product or certify it."""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator
ROOT=Path(__file__).resolve().parents[1]
IGNORED={'.venv','__pycache__','.pytest_cache','.git'}

class UniqueLoader(yaml.SafeLoader): pass

def mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    result={}
    for kn,vn in node.value:
        key=loader.construct_object(kn,deep=deep)
        if key in result: raise ValueError('DUPLICATE_YAML_KEY:'+str(key))
        result[key]=loader.construct_object(vn,deep=deep)
    return result
UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)

def load_yaml(path): return yaml.load(path.read_text(encoding='utf-8'),Loader=UniqueLoader)

def check_dag(graph):
    pending=set(); done=set()
    def visit(node):
        if node in pending: raise ValueError('DEPENDENCY_CYCLE:'+node)
        if node in done:return
        if node not in graph:raise ValueError('UNKNOWN_DEPENDENCY:'+node)
        pending.add(node)
        for dep in graph[node]:visit(dep)
        pending.remove(node);done.add(node)
    for node in graph:visit(node)

def manifest_files(root):
    path=root/'PACKAGE_CONTENTS.sha256'
    if not path.is_file():raise ValueError('PACKAGE_MANIFEST_MISSING')
    entries={}
    for line in path.read_text(encoding='utf-8').splitlines():
        h, sep, name=line.partition('  ')
        p=Path(name)
        if not sep or not re.fullmatch('[0-9a-f]{64}',h) or p.is_absolute() or '..' in p.parts or not name or name in entries:
            raise ValueError('INVALID_PACKAGE_MANIFEST')
        target=root/p
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
            raise ValueError('INVALID_PACKAGE_FILE:'+name)
        if hashlib.sha256(target.read_bytes()).hexdigest()!=h:raise ValueError('PACKAGE_DIGEST_MISMATCH:'+name)
        entries[name]=h
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and not IGNORED.intersection(p.relative_to(root).parts) and p.name!='PACKAGE_CONTENTS.sha256'}
    if set(entries)!=actual:raise ValueError('PACKAGE_MANIFEST_INVENTORY_MISMATCH')
    return entries

def validate(root:Path=ROOT,verify_lock:bool=False):
    errors=[];counts={}
    def guarded(label, fn):
        try:fn()
        except Exception as exc: errors.append(label+': '+type(exc).__name__+': '+str(exc))
    yamls=[p for p in root.rglob('*.yaml') if not IGNORED.intersection(p.relative_to(root).parts)]
    for p in yamls:guarded(str(p.relative_to(root)),lambda p=p:load_yaml(p))
    counts['yaml_files']=len(yamls)
    schemas={}
    for p in (root/'contracts/schemas').glob('*.schema.json'):
        def schema_check(p=p):
            x=json.loads(p.read_text());Draft202012Validator.check_schema(x)
            schemas[p.name]=x
        guarded('schema:'+p.name,schema_check)
    counts['json_schemas']=len(schemas)
    manifests={};acceptances=[]
    for d in sorted((root/'skills').iterdir()):
        if not d.is_dir():continue
        def skill_check(d=d):
            for name in ['SKILL.md','manifest.yaml','implementation.yaml','acceptance.yaml','runbook.md']:
                if not (d/name).is_file():raise ValueError('MISSING:'+name)
            text=(d/'SKILL.md').read_text(encoding='utf-8');parts=text.split('---',2)
            if len(parts)!=3 or parts[0].strip():raise ValueError('INVALID_FRONTMATTER')
            front=yaml.load(parts[1],Loader=UniqueLoader)
            if front.get('name')!=d.name or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',d.name) or len(d.name)>64:
                raise ValueError('INVALID_SKILL_NAME')
            if not front.get('description') or len(front['description'])>1024 or len(text.splitlines())>=500:
                raise ValueError('SKILL_DISCLOSURE_LIMIT')
            m=load_yaml(d/'manifest.yaml')
            Draft202012Validator(schemas['skill-manifest.schema.json']).validate(m)
            if m['id']!=d.name:raise ValueError('MANIFEST_ID_MISMATCH')
            manifests[d.name]=m
            acc=load_yaml(d/'acceptance.yaml')
            if not acc['cases'] or acc['product_acceptance_status']!='NOT_RUN':raise ValueError('NATIVE_ACCEPTANCE_NOT_HONEST')
            for case in acc['cases']:
                if case['status']!='NOT_RUN' or not all(case.get(k) for k in ['given','when','then','evidence_required']):raise ValueError('INVALID_ACCEPTANCE')
                acceptances.append(case['id'])
        guarded('skill:'+d.name,skill_check)
    counts['skills']=len(manifests);counts['skill_acceptance_cases']=len(acceptances)
    guarded('skill-dag',lambda:check_dag({k:v['dependencies'] for k,v in manifests.items()}))
    def batches():
        obj=load_yaml(root/'roadmap/implementation-batches.yaml');seq=obj['batches']
        check_dag({b['id']:b['depends_on'] for b in seq})
        where={}
        for i,b in enumerate(seq):
            for j,s in enumerate(b['skills']):
                if s in where or s not in manifests:raise ValueError('DUPLICATE_OR_UNKNOWN_BATCH_SKILL:'+s)
                where[s]=(i,j)
        if set(where)!=set(manifests)-{'elmos-assurance-orchestrator'}:raise ValueError('UNSCHEDULED_SKILL')
        for s,pos in where.items():
            for dep in manifests[s]['dependencies']:
                if dep not in where or where[dep]>=pos:raise ValueError('BATCH_DEPENDENCY_ORDER:'+s+'->'+dep)
    guarded('batches',batches)
    domain_count=0;native=[]
    for d in sorted((root/'domain-packs').iterdir()):
        if not d.is_dir():continue
        domain_count+=1
        def domain(d=d):
            acc=load_yaml(d/'acceptance.yaml');ids={c['id'] for c in acc['cases']};native.extend(ids)
            route=load_yaml(root/'golden-routes'/d.name/'route.yaml')
            if set(route['acceptance_case_ids'])!=ids or route['native_evidence']!='NOT_RUN':raise ValueError('GOLDEN_ROUTE_CASE_MISMATCH')
            w=load_yaml(root/'workflows'/(d.name+'.yaml'))
            graph={s['id']:s['depends_on'] for s in w['steps']};check_dag(graph)
            if 'smoke' not in graph['regression'] or 'regression' not in graph['seal'] or 'audit' not in graph['decision']:
                raise ValueError('WORKFLOW_GATE_ORDER')
        guarded('domain:'+d.name,domain)
    counts['domain_packs']=domain_count;counts['native_route_acceptance_cases']=len(native)
    if len(acceptances+native)!=len(set(acceptances+native)):errors.append('DUPLICATE_ACCEPTANCE_ID')
    def api():
        spec=load_yaml(root/'contracts/openapi/assurance-control.yaml');opids=[]
        if spec['openapi']!='3.1.1':raise ValueError('UNAPPROVED_OPENAPI_BASELINE')
        def resolve(ref):
            if not ref.startswith('#/'):raise ValueError('NONLOCAL_REFERENCE')
            v=spec
            for seg in ref[2:].split('/'):v=v[seg.replace('~1','/').replace('~0','~')]
            return v
        def walk(x):
            if isinstance(x,dict):
                if '$ref'in x:resolve(x['$ref'])
                for y in x.values():walk(y)
            elif isinstance(x,list):
                for y in x:walk(y)
        walk(spec)
        for path,item in spec['paths'].items():
            params=set(re.findall(r'\{([^}]+)\}',path))
            for method,op in item.items():
                if method not in {'get','post','put','patch','delete','head','options'}:continue
                opids.append(op['operationId'])
                if not op.get('security') or not op.get('x-required-permission'):raise ValueError('UNAUTHORIZED_API_CONTRACT')
                pp=[resolve(p['$ref']) if '$ref'in p else p for p in op.get('parameters',[])]
                if {p['name']for p in pp if p['in']=='path'and p.get('required')}!=params:raise ValueError('PATH_PARAMETER_MISMATCH')
                if method in {'post','put','patch','delete'}:
                    if not {'Idempotency-Key','If-Match'}<={p['name']for p in pp if p['in']=='header'and p.get('required')}:raise ValueError('WRITE_WITHOUT_CONCURRENCY_GUARD')
                    if 'requestBody'not in op:raise ValueError('MISSING_WRITE_BODY')
                if not op.get('responses'):raise ValueError('MISSING_RESPONSE')
        if len(opids)!=len(set(opids)):raise ValueError('DUPLICATE_OPERATION_ID')
        counts['api_operations']=len(opids)
    guarded('openapi-static-references-and-policy',api)
    def examples():
        rows=load_yaml(root/'examples/index.yaml')['examples']
        for row in rows:
            x=json.loads((root/row['path']).read_text())
            Draft202012Validator(schemas[row['schema']]).validate(x)
        if {r['schema']for r in rows}!=set(schemas):raise ValueError('SCHEMA_WITHOUT_EXAMPLE')
        counts['schema_examples']=len(rows)
    guarded('schema-examples',examples)
    def package():
        m=load_yaml(root/'package.yaml')
        if m['skills_count']!=len(manifests):raise ValueError('SKILL_COUNT_MISMATCH')
        for flag in ['full_product_implemented','native_route_certified','lean_checked','ethen_signed','accredited_certification']:
            if m['claims'][flag]is not False:raise ValueError('UNSUPPORTED_PRODUCT_CLAIM:'+flag)
        if m['canonical_route_delta']!=0:raise ValueError('UNEXPECTED_ROUTE_DELTA')
    guarded('package-manifest',package)
    if verify_lock:guarded('package-sha256-inventory',lambda:manifest_files(root))
    return {'status':'PASS'if not errors else 'FAIL','kind':'PACKAGE_STRUCTURE_ONLY_NOT_PRODUCT_CERTIFICATION','counts':counts,'errors':errors,'native_validation':'NOT_RUN','lock_checked':verify_lock}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--verify-lock',action='store_true');ap.add_argument('--output',type=Path);a=ap.parse_args()
    result=validate(verify_lock=a.verify_lock);raw=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(raw,encoding='utf-8')
    print(raw,end='');return 0 if result['status']=='PASS'else 1
if __name__=='__main__':raise SystemExit(main())
