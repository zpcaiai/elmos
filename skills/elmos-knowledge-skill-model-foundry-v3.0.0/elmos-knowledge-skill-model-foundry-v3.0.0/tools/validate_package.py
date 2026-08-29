#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, sys
from collections import defaultdict
from pathlib import Path
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
YAML_LOADER = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
def load_yaml(path: Path):
    return yaml.load(path.read_text(encoding='utf-8'), Loader=YAML_LOADER)

ap = argparse.ArgumentParser()
ap.add_argument('--verify-hashes', action='store_true')
args = ap.parse_args()
errors=[]
try:
    manifest=load_yaml(ROOT/'manifest.yaml')
    catalog=load_yaml(ROOT/'registry/skill-catalog.yaml')
    schema=json.loads((ROOT/'schemas/skill-contract-v3.schema.json').read_text(encoding='utf-8'))
except Exception as e:
    raise SystemExit(f'ERROR package bootstrap parse: {e}')
items=catalog['spec']['skills']
contract_validator=Draft202012Validator(schema)
ids=set(); packs=set(); dependency_refs=set(); graph=defaultdict(list)
required_case_counts={'positive':8,'negative':8,'ambiguous':4,'adversarial':4}
required_files=[
    'SKILL.md','skill.yaml','evals/contract.yaml','evals/cases.yaml',
    'policies/execution.yaml','references/implementation-notes.md','tests/conformance.yaml'
]
for item in items:
    sid=item['id']; pack=item['pack']; packs.add(pack)
    if sid in ids: errors.append(f'duplicate id: {sid}')
    ids.add(sid)
    if len(sid)>64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', sid): errors.append(f'invalid id: {sid}')
    md=ROOT/item['path']; root=md.parent; y=root/'skill.yaml'
    for rel in required_files:
        p=root/rel
        if not p.exists(): errors.append(f'missing {rel}: {sid}')
        elif p.stat().st_size == 0: errors.append(f'empty {rel}: {sid}')
    if not y.exists(): continue
    try: obj=load_yaml(y)
    except Exception as e: errors.append(f'yaml parse {sid}: {e}'); continue
    for e in contract_validator.iter_errors(obj): errors.append(f'schema {sid}: {e.json_path}: {e.message}')
    if obj['metadata']['name'] != sid: errors.append(f'name mismatch: {sid}')
    if obj['metadata']['pack'] != pack: errors.append(f'pack mismatch: {sid}')
    if obj['metadata']['version'] != manifest['metadata']['version']: errors.append(f'version mismatch: {sid}')
    if not obj['metadata'].get('owner') or obj['metadata'].get('owner') == 'TBD': errors.append(f'owner missing: {sid}')
    deps=obj['spec'].get('dependencies', [])
    if sid in deps: errors.append(f'self dependency: {sid}')
    dependency_refs.update(deps); graph[sid].extend(deps)
    if not obj['spec']['tools'].get('defaultDeny'): errors.append(f'tools not default deny: {sid}')
    if not obj['spec']['rollback'].get('required'): errors.append(f'rollback not required: {sid}')
    if obj['spec']['learning'].get('globalTrainingEligible') is not False: errors.append(f'global training must default false: {sid}')
    if obj['spec'].get('maturity',{}).get('status') not in {'specification-ready','implemented','E1','E2','E3','E4','E5'}:
        errors.append(f'invalid maturity status: {sid}')
    if md.exists():
        text=md.read_text(encoding='utf-8')
        m=re.match(r'^---\n(.*?)\n---\n', text, re.S)
        if not m: errors.append(f'frontmatter missing: {sid}')
        else:
            try: fm=yaml.load(m.group(1), Loader=YAML_LOADER) or {}
            except Exception as e: errors.append(f'frontmatter parse {sid}: {e}'); fm={}
            if fm.get('name') != sid: errors.append(f'frontmatter name mismatch: {sid}')
            if len(fm.get('description',''))>1024: errors.append(f'description too long: {sid}')
    ep=root/'evals/contract.yaml'; cp=root/'evals/cases.yaml'
    if ep.exists() and cp.exists():
        try:
            ec=load_yaml(ep) or {}; cases=load_yaml(cp) or {}
        except Exception as e:
            errors.append(f'eval parse {sid}: {e}'); ec={}; cases={}
        activation=ec.get('activation',{})
        for kind, minimum in required_case_counts.items():
            declared=activation.get(kind+'Required')
            if declared != minimum: errors.append(f'eval declared count {sid}/{kind}: {declared} != {minimum}')
            actual=cases.get(kind)
            if not isinstance(actual,list) or len(actual)<minimum: errors.append(f'eval actual count {sid}/{kind}: {len(actual or [])} < {minimum}')
        for row in cases.get('positive',[]):
            if row.get('shouldTrigger') is not True: errors.append(f'positive eval malformed: {sid}')
        for row in cases.get('negative',[]):
            if row.get('shouldTrigger') is not False: errors.append(f'negative eval malformed: {sid}')
        for kind in ('ambiguous','adversarial'):
            for row in cases.get(kind,[]):
                if not row.get('expected'): errors.append(f'{kind} eval malformed: {sid}')
    for rel in ('policies/execution.yaml','tests/conformance.yaml'):
        p=root/rel
        if p.exists():
            try: load_yaml(p)
            except Exception as e: errors.append(f'parse {rel} {sid}: {e}')
unknown=sorted(dependency_refs-ids)
for dep in unknown: errors.append(f'unresolved dependency: {dep}')
# Tarjan SCC: executable dependency graph must be acyclic.
index=0; indices={}; low={}; stack=[]; on=set(); cycles=[]
def strong(v):
    global index
    indices[v]=low[v]=index; index+=1; stack.append(v); on.add(v)
    for w in graph.get(v,[]):
        if w not in ids: continue
        if w not in indices:
            strong(w); low[v]=min(low[v],low[w])
        elif w in on: low[v]=min(low[v],indices[w])
    if low[v]==indices[v]:
        comp=[]
        while True:
            w=stack.pop(); on.remove(w); comp.append(w)
            if w==v: break
        if len(comp)>1: cycles.append(comp)
for sid in ids:
    if sid not in indices: strong(sid)
for comp in cycles: errors.append('dependency cycle: '+','.join(sorted(comp)))
if manifest['metadata']['atomicSkillCount'] != len(items): errors.append('atomic skill count mismatch')
meta_dirs=[p for p in (ROOT/'skills/meta').iterdir() if p.is_dir()]
if manifest['metadata']['metaSkillCount'] != len(meta_dirs): errors.append('meta skill count mismatch')
if manifest['metadata']['packCount'] != len(manifest['spec']['packs']): errors.append('pack count mismatch')
for pack in manifest['spec']['packs']:
    md=ROOT/'skills/meta'/pack/'SKILL.md'; ev=ROOT/'skills/meta'/pack/'evals/activation.json'
    if not md.exists(): errors.append(f'missing meta skill: {pack}')
    else:
        text=md.read_text(encoding='utf-8'); m=re.match(r'^---\n(.*?)\n---\n', text, re.S)
        if not m: errors.append(f'meta frontmatter missing: {pack}')
        else:
            try: yaml.load(m.group(1), Loader=YAML_LOADER)
            except Exception as e: errors.append(f'meta frontmatter parse {pack}: {e}')
    if not ev.exists(): errors.append(f'missing meta activation eval: {pack}')
    else:
        try: json.loads(ev.read_text(encoding='utf-8'))
        except Exception as e: errors.append(f'meta eval parse {pack}: {e}')
    if not (ROOT/'skills/atomic'/pack).exists(): errors.append(f'missing atomic pack dir: {pack}')
# Parse non-skill registries, policies, pipelines and schemas exactly once.
for folder in ('registry','schemas','policies','pipelines','observability','examples'):
    base=ROOT/folder
    if not base.exists(): continue
    for path in base.rglob('*'):
        if not path.is_file(): continue
        try:
            if path.suffix in {'.yaml','.yml'}: load_yaml(path)
            elif path.suffix == '.json': json.loads(path.read_text(encoding='utf-8'))
        except Exception as e: errors.append(f'parse error {path.relative_to(ROOT)}: {e}')
if args.verify_hashes:
    sums=ROOT/'SHA256SUMS'
    if not sums.exists(): errors.append('SHA256SUMS missing')
    else:
        for line in sums.read_text(encoding='utf-8').splitlines():
            if not line.strip(): continue
            try: expected, rel=line.split('  ',1)
            except ValueError: errors.append(f'invalid hash line: {line[:80]}'); continue
            p=ROOT/rel
            if not p.exists(): errors.append(f'hash target missing: {rel}'); continue
            actual=hashlib.sha256(p.read_bytes()).hexdigest()
            if actual != expected: errors.append(f'hash mismatch: {rel}')
if errors:
    print('\n'.join('ERROR '+x for x in errors)); sys.exit(1)
print(f'OK: {len(items)} atomic skills, {len(meta_dirs)} meta skills, {len(packs)} packs; schema, DAG, eval, policy, content and count validation passed')
