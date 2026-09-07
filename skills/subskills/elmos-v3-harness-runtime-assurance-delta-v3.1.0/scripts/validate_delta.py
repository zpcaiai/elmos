#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import py_compile
import sys
from collections import defaultdict, deque
from pathlib import Path

try:
    import yaml
    import jsonschema
except ImportError as exc:
    raise SystemExit("Install pyyaml and jsonschema") from exc

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []


def fail(x: str) -> None:
    errors.append(x)


def y(path: Path):
    try:
        return yaml.safe_load(path.read_text(encoding='utf-8'))
    except Exception as exc:
        fail(f"YAML parse failed {path.relative_to(ROOT)}: {exc}")
        return None


def j(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        fail(f"JSON parse failed {path.relative_to(ROOT)}: {exc}")
        return None

for p in ROOT.rglob('*.yaml'):
    y(p)
for p in ROOT.rglob('*.yml'):
    y(p)
for p in ROOT.rglob('*.json'):
    j(p)

manifest = y(ROOT / 'DELTA_MANIFEST.yaml') or {}
if manifest.get('metadata', {}).get('incrementalOnly') is not True:
    fail('manifest is not incrementalOnly')
if manifest.get('spec', {}).get('base', {}).get('exactVersion') != '3.0.0':
    fail('base exactVersion must be 3.0.0')

# Ensure no full base package was accidentally copied.
for forbidden in ['kernels', 'domain-packs', 'semantic-compiler/profiles', 'golden-routes', 'validation/etgb-v1.1']:
    if (ROOT / forbidden).exists() or (ROOT / 'payload' / forbidden).exists():
        fail(f'forbidden base content present: {forbidden}')

skills = sorted((ROOT / 'payload/skills/extensions').glob('P*/elmos-*'))
if len(skills) != 13:
    fail(f'expected 13 extension skills, found {len(skills)}')
required = {'SKILL.md','manifest.yaml','acceptance.yaml','implementation.yaml','runbook.md'}
names: set[str] = set()
deps: dict[str, set[str]] = {}
base_names = {
    'elmos-goal-specification-kernel','elmos-repository-intelligence-kernel','elmos-repository-semantic-compiler-kernel',
    'elmos-agentic-reasoning-kernel','elmos-transformation-kernel','elmos-proof-verification-kernel',
    'elmos-harness-runtime-kernel','elmos-certification-kernel'
}
for d in skills:
    if required - {x.name for x in d.iterdir() if x.is_file()}:
        fail(f'{d.relative_to(ROOT)} missing required files')
    m = y(d/'manifest.yaml') or {}
    name = m.get('metadata', {}).get('name')
    if name in names:
        fail(f'duplicate skill {name}')
    names.add(name)
    if m.get('metadata', {}).get('labels', {}).get('routable') != 'false':
        fail(f'{name} is routable')
    deps[name] = {x['name'] for x in m.get('spec', {}).get('dependencies', []) if x.get('kind') == 'kernel-extension'}
    for x in m.get('spec', {}).get('dependencies', []):
        if x.get('kind') == 'base-routable-owner' and x.get('name') not in base_names:
            fail(f'{name} references unknown base owner {x.get("name")}')

for name, d in deps.items():
    unknown = d - names
    if unknown:
        fail(f'{name} has unknown extension deps {sorted(unknown)}')
indegree = {n: len(d) for n,d in deps.items()}
rev: dict[str,set[str]] = defaultdict(set)
for n, ds in deps.items():
    for d in ds: rev[d].add(n)
q = deque([n for n,v in indegree.items() if v == 0]); visited = 0
while q:
    n=q.popleft(); visited += 1
    for x in rev[n]:
        indegree[x]-=1
        if indegree[x]==0: q.append(x)
if visited != len(deps): fail('extension dependency graph has a cycle')

registry = y(ROOT/'payload/skills/extensions/registry.v3.1.yaml') or {}
reg = {x.get('name') for x in registry.get('spec',{}).get('entries',[])}
if reg != names: fail('extension registry mismatch')
if registry.get('spec',{}).get('routable') is not False: fail('registry must be non-routable')

schemas = {}
for p in sorted((ROOT/'payload/contracts/schemas/delta-v3.1').glob('*.schema.json')):
    obj=j(p)
    if obj:
        try:
            jsonschema.Draft202012Validator.check_schema(obj)
            schemas[p.stem.replace('.schema','')] = obj
        except Exception as exc: fail(f'schema invalid {p.name}: {exc}')
if len(schemas) != 15: fail(f'expected 15 schemas, found {len(schemas)}')
for p in sorted((ROOT/'payload/contracts/examples/delta-v3.1').glob('*.example.json')):
    name=p.name.replace('.example.json','')
    obj=j(p)
    if name not in schemas: fail(f'example has no schema {name}')
    elif obj is not None:
        try: jsonschema.validate(obj, schemas[name])
        except Exception as exc: fail(f'example invalid {p.name}: {exc}')

for p in list((ROOT/'payload/reference-implementation').rglob('*.py')) + list((ROOT/'scripts').glob('*.py')):
    try: py_compile.compile(str(p), doraise=True)
    except Exception as exc: fail(f'python compile failed {p.relative_to(ROOT)}: {exc}')

expected_hashes = j(ROOT/'PAYLOAD_HASHES.json') or {}
actual_files = sorted(p for p in (ROOT/'payload').rglob('*') if p.is_file() and '__pycache__' not in p.parts)
actual = {str(p.relative_to(ROOT/'payload')): hashlib.sha256(p.read_bytes()).hexdigest() for p in actual_files}
if expected_hashes != actual: fail('payload hash manifest mismatch')

report={'status':'PASS' if not errors else 'FAIL','errors':errors,'counts':{'extensionSkills':len(skills),'schemas':len(schemas),'payloadFiles':len(actual_files)}}
print(json.dumps(report,indent=2))
if errors: raise SystemExit(1)
