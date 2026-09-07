#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys
from collections import defaultdict, deque
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
SKILL_ROOT_FILES={'SKILL.md','contract.yaml','implementation.yaml','acceptance.yaml','evidence.yaml','domain-model.yaml','native-test-matrix.yaml','threat-model.yaml','version-support.yaml','observability.yaml','api-contract.yaml'}
SKILL_NESTED={'references/IMPLEMENTATION_GUIDE.md','scripts/validate_artifacts.py'}
ADAPTER_FILES={'adapter.yaml','capability-map.yaml','lowering-contract.yaml','conformance.yaml','version-support.yaml','native-test-matrix.yaml','threat-model.yaml','deployment-profile.yaml'}
def y(path):return yaml.safe_load(path.read_text(encoding='utf-8'))
def cycle(g):
 indeg={n:0 for n in g};rev=defaultdict(list)
 for n,deps in g.items():
  for d in deps:indeg[n]+=1;rev[d].append(n)
 q=deque(n for n,v in indeg.items() if v==0);seen=0
 while q:
  n=q.popleft();seen+=1
  for c in rev[n]:
   indeg[c]-=1
   if indeg[c]==0:q.append(c)
 return seen!=len(g)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--strict',action='store_true');ap.add_argument('--skip-tests',action='store_true');args=ap.parse_args()
 errors=[];warnings=[];metrics={}
 def err(x):errors.append(x)
 required=['SKILL.md','README.md','package.yaml','CHANGELOG.md','REFERENCES.md','SKILL_INDEX.md','ADAPTER_INDEX.md','PACKAGE_RELATIONSHIP.md']
 for f in required:
  if not (ROOT/f).is_file():err('missing root file '+f)
 manifest=y(ROOT/'package.yaml');expected=manifest['spec']['counts'];role=manifest['spec']['packageRole']
 registry=y(ROOT/'catalog/skill-registry.yaml')['spec']['skills'];by={r['name']:r for r in registry}
 dirs=sorted(p for p in (ROOT/'agent-skills/runtime').iterdir() if p.is_dir());metrics['skills']=len(dirs);sf=0;g={};external_edges=0
 for d in dirs:
  roots={p.name for p in d.iterdir() if p.is_file()};nested={p.relative_to(d).as_posix() for p in d.rglob('*') if p.is_file() and p.parent!=d}
  if roots!=SKILL_ROOT_FILES:err(f'{d.name}: skill root inventory mismatch')
  if nested!=SKILL_NESTED:err(f'{d.name}: skill nested inventory mismatch')
  sf+=sum(1 for p in d.rglob('*') if p.is_file())
  c=y(d/'contract.yaml')['spec'];local=c.get('dependencies',[]);ext=c.get('externalDependencies',[]);g[d.name]=local;external_edges+=len(ext)
  if d.name not in by:err(f'{d.name}: missing registry entry')
  else:
   if by[d.name].get('depends_on',[])!=local:err(f'{d.name}: registry/local dependency mismatch')
   if by[d.name].get('external_depends_on',[])!=[x['skill'] for x in ext]:err(f'{d.name}: registry/external dependency mismatch')
  for dep in local:
   if dep not in by:err(f'{d.name}: missing local dependency {dep}')
  for x in ext:
   if x.get('package')==manifest['metadata']['name']:err(f'{d.name}: external dependency points to self')
  if c.get('packageRole')!=role:err(f'{d.name}: package role mismatch')
 metrics['perSkillFiles']=sf;metrics['externalDependencyEdges']=external_edges
 if set(by)!=set(p.name for p in dirs):err('skill registry/directory mismatch')
 if cycle(g):err('local dependency cycle')
 adapters=sorted(p for p in (ROOT/'target-adapters').iterdir() if p.is_dir());metrics['adapters']=len(adapters);af=0
 for d in adapters:
  files={p.name for p in d.iterdir() if p.is_file()};af+=len(files)
  if files!=ADAPTER_FILES:err(f'{d.name}: adapter inventory mismatch')
 metrics['perAdapterFiles']=af
 ar=y(ROOT/'catalog/adapter-registry.yaml')['spec']['adapters']
 if set(r['name'] for r in ar)!=set(d.name for d in adapters):err('adapter registry/directory mismatch')
 # Parse machine-readable assets.
 for p in list((ROOT/'contracts/schemas').glob('*.json'))+list((ROOT/'contracts/examples').glob('*.json')):
  try:json.loads(p.read_text())
  except Exception as e:err(f'{p.relative_to(ROOT)}: JSON {e}')
 for p in list((ROOT/'catalog').glob('*.yaml'))+list((ROOT/'workflows').glob('*.yaml'))+list((ROOT/'golden-routes').glob('*/route.yaml')):
  try:y(p)
  except Exception as e:err(f'{p.relative_to(ROOT)}: YAML {e}')
 metrics['schemas']=len(list((ROOT/'contracts/schemas').glob('*.schema.json')));metrics['examples']=len(list((ROOT/'contracts/examples').glob('*.example.json')))
 metrics['workflows']=len(list((ROOT/'workflows').glob('*.yaml')));metrics['policies']=len(list((ROOT/'policies/rego').glob('*.rego')));metrics['policyTests']=sum(1 for p in (ROOT/'policies/tests').iterdir() if p.is_file())
 metrics['migrations']=len(list((ROOT/'database/postgres').glob('[0-9][0-9][0-9]_*.sql')));metrics['goldenRoutes']=len(list((ROOT/'golden-routes').glob('*/route.yaml')))
 metrics['docs']=len(list((ROOT/'docs').glob('*.md')));metrics['referenceModules']=len([p for p in (ROOT/'reference_kernel/elmos_ai_factory').glob('*.py') if p.name!='__init__.py'])
 tt='\n'.join(p.read_text() for p in (ROOT/'tests').glob('test_*.py'));metrics['referenceTests']=len(re.findall(r'^\s*def test_',tt,re.M));metrics['nativeFixtureFiles']=sum(1 for p in (ROOT/'native-fixtures').rglob('*') if p.is_file())
 trace=y(ROOT/'implementation/traceability.yaml')['spec']['skills'];metrics['traceability']=len(trace)
 batches=y(ROOT/'implementation/batches.yaml')['spec']['batches'];metrics['implementationBatches']=len(batches);metrics['implementationTasks']=sum(len(b.get('tasks',[])) for b in batches)
 for k,v in metrics.items():
  if expected.get(k)!=v:err(f'manifest {k}: expected={expected.get(k)} actual={v}')
 # Compile and run reference tests.
 py=[str(p) for p in list((ROOT/'reference_kernel').rglob('*.py'))+list((ROOT/'scripts').glob('*.py'))+list((ROOT/'tests').glob('*.py'))]
 cp=subprocess.run([sys.executable,'-m','py_compile',*py],cwd=ROOT,text=True,capture_output=True)
 if cp.returncode:err('python compile: '+cp.stderr[-1000:])
 summary='skipped'
 if not args.skip_tests:
  env=dict(os.environ);env['PYTHONPATH']=str(ROOT)
  tr=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,text=True,capture_output=True,env=env)
  summary=(tr.stdout+tr.stderr)[-5000:]
  if tr.returncode:err('reference tests failed: '+summary)
 for sh in ['validate.sh','install.sh','uninstall.sh','build-release.sh']:
  r=subprocess.run(['bash','-n',str(ROOT/sh)],text=True,capture_output=True)
  if r.returncode:err(f'{sh}: shell syntax')
 # Symlink and obvious secret checks.
 for p in ROOT.rglob('*'):
  if p.is_symlink():err(f'unsafe symlink {p.relative_to(ROOT)}')
 secret_re=re.compile(r'(AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|sk-[A-Za-z0-9]{24,})')
 for p in ROOT.rglob('*'):
  if not p.is_file():continue
  try:t=p.read_text(encoding='utf-8')
  except UnicodeDecodeError:continue
  if secret_re.search(t):err(f'obvious secret pattern {p.relative_to(ROOT)}')
 report={'status':'PASS' if not errors else 'FAIL','metrics':metrics,'warnings':warnings,'errors':errors,'testSummary':summary}
 print(json.dumps(report,ensure_ascii=False,indent=2));return 0 if not errors else 1
if __name__=='__main__':raise SystemExit(main())
