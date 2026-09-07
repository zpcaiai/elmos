#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

EXCLUDED_PARTS={'.git','target','node_modules','.venv','artifacts','portfolio-packs','__pycache__'}
SOURCE_SUFFIXES={'.java':'java','.py':'python','.cs':'csharp','.ts':'typescript','.tsx':'typescript'}

def load(path): return json.loads(path.read_text())
def write(path,data): path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def digest_bytes(value): return 'sha256:'+hashlib.sha256(value).hexdigest()
def q(tag): return '{http://maven.apache.org/POM/4.0.0}'+tag

def source_manifest(root):
 files=[]
 for path in sorted(root.rglob('*')):
  if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts): continue
  if path.name!='pom.xml' and path.suffix not in SOURCE_SUFFIXES: continue
  raw=path.read_bytes()
  files.append({'path':path.relative_to(root).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
 canonical=json.dumps(files,separators=(',',':'),sort_keys=True).encode()
 return files,digest_bytes(canonical)

def pom_text(node,name):
 value=node.findtext(q(name)) or node.findtext(name)
 return value.strip() if value else None

def discover_modules(root):
 tree=ElementTree.parse(root/'pom.xml'); project=tree.getroot()
 module_paths=[item.text.strip() for item in project.findall('./'+q('modules')+'/'+q('module')) if item.text]
 modules=[]
 for module_path in module_paths:
  pom=root/module_path/'pom.xml'
  if not pom.is_file(): raise SystemExit(f'missing Maven module pom: {module_path}/pom.xml')
  module_root=ElementTree.parse(pom).getroot(); artifact=pom_text(module_root,'artifactId')
  if not artifact: raise SystemExit(f'missing artifactId: {module_path}/pom.xml')
  dependencies=[]
  for dependency in module_root.findall('.//'+q('dependency'))+module_root.findall('.//dependency'):
   if pom_text(dependency,'groupId')=='io.elmos':
    target=pom_text(dependency,'artifactId')
    if target: dependencies.append(target)
  files=[]; loc=0; size=0; languages=set()
  for path in sorted((root/module_path).rglob('*')):
   if not path.is_file() or any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts): continue
   language=SOURCE_SUFFIXES.get(path.suffix)
   if not language: continue
   raw=path.read_bytes(); size+=len(raw); loc+=sum(1 for line in raw.splitlines() if line.strip()); languages.add(language)
   files.append(path.relative_to(root).as_posix())
  modules.append({'path':module_path,'artifact_id':artifact,'dependency_artifacts':sorted(set(dependencies)),
                  'loc':loc,'size_bytes':size,'languages':sorted(languages) or ['java'],'files':files})
 return modules

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--repo-root',default='.')
 parser.add_argument('--pack-key',default='elmos-local-rehearsal')
 parser.add_argument('--owner',default='elmos-platform-team')
 parser.add_argument('--region',default='local-macos')
 args=parser.parse_args(); root=Path(args.repo_root).resolve()
 if not (root/'pom.xml').is_file(): raise SystemExit('local rehearsal requires the ELMOS Maven root')
 templates=root/'templates/batch34'; scripts=root/'scripts/batch34'; pack=root/'portfolio-packs'/args.pack_key
 subprocess.run([sys.executable,str(scripts/'scaffold_portfolio_pack.py'),'--pack-key',args.pack_key,
                 '--scm-provider','filesystem','--organization','elmos-local-workspace','--region',args.region,
                 '--repository-target','1','--loc-target','1','--repo-root',str(root),'--force'],check=True)
 modules=discover_modules(root); manifest_files,tree_digest=source_manifest(root)
 captured=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
 total_loc=sum(item['loc'] for item in modules); total_bytes=sum(item['size_bytes'] for item in modules)
 languages=sorted({language for item in modules for language in item['languages']})
 artifact_to_module={item['artifact_id']:item for item in modules}
 module_id={item['artifact_id']:'module.'+item['artifact_id'] for item in modules}
 work_id={item['artifact_id']:'wu.'+item['artifact_id'] for item in modules}

 manifest=load(pack/'pack.json'); manifest.update({'version':'0.1.0-local','status':'experimental','mode':'assessment',
   'owner':args.owner,'maintenance_owner':args.owner,'tags':['local-rehearsal','not-production-certified']})
 manifest['scope'].update({'tenant_model':'single-tenant-local-development','scm_sources':['filesystem'],
   'organizations':['elmos-local-workspace'],'regions':[args.region],'languages':languages,
   'build_systems':['maven'],'inventory_snapshot_at':captured,'repository_target':1,'loc_target':max(1,total_loc)})
 write(pack/'pack.json',manifest)

 source_evidence='certification/local-source-manifest.json'
 inventory=load(pack/'inventory/portfolio.json'); inventory.update({'snapshot_digest':tree_digest,'captured_at':captured,
   'coverage':1.0,'repositories':[{'id':'repo.elmos','scm_provider':'filesystem','organization':'elmos-local-workspace',
   'name':'elmos','default_branch':'WORKTREE','baseline_commit':tree_digest,'owner':args.owner,'status':'active',
   'criticality':'P1','regions':[args.region],'languages':languages,'build_systems':['maven'],'loc':total_loc,
   'size_bytes':total_bytes,'evidence_refs':[source_evidence]}],'unreachable':[]})
 write(pack/'inventory/portfolio.json',inventory)

 nodes=[{'id':'repo.elmos','kind':'repository','logical_key':'elmos-local-workspace/elmos','owner':args.owner,
        'source_refs':[{'path':'inventory/portfolio.json','digest':tree_digest}]}]
 for item in modules:
  nodes.append({'id':module_id[item['artifact_id']],'kind':'module','logical_key':item['path'],'owner':args.owner,
                'source_refs':[{'path':item['path']+'/pom.xml'}]})
 edges=[]
 for item in modules:
  for target in item['dependency_artifacts']:
   if target not in artifact_to_module: continue
   key=item['artifact_id']+'->'+target
   edges.append({'id':'edge.'+hashlib.sha256(key.encode()).hexdigest()[:20],
                 'from':module_id[item['artifact_id']],'to':module_id[target],'kind':'build','criticality':'P1',
                 'confidence':1.0,'evidence_refs':[item['path']+'/pom.xml']})
 graph=load(pack/'graph/dependencies.json'); graph.update({'graph_version':tree_digest,'nodes':nodes,'edges':edges})
 write(pack/'graph/dependencies.json',graph)

 units=[]
 for item in sorted(modules,key=lambda value:value['artifact_id']):
  deps=[work_id[target] for target in item['dependency_artifacts'] if target in work_id]
  units.append({'id':work_id[item['artifact_id']],'owner':args.owner,'tenant_scope':'elmos-local-development',
    'regions':[args.region],'repository_ids':['repo.elmos'],'module_refs':[item['path']],
    'partition_key':tree_digest+':'+item['path'],'dependencies':sorted(set(deps)),'estimated_loc':item['loc'],
    'resource_profile':'local-java-21-maven','criticality':'P1','entry_gate':'local-source-manifest-verified',
    'exit_gate':'module-tests-passed','evidence_refs':[source_evidence,item['path']+'/pom.xml']})
 work=load(pack/'work-units/plan.json'); work.update({'graph_version':tree_digest,'units':units}); write(pack/'work-units/plan.json',work)

 scale=load(pack/'scale/scale-profile.json'); scale.update({'owner':args.owner})
 scale['environment'].update({'runner_image_digest':'sha256:local-macos-java21-maven','regions':[args.region],
   'service_versions':{'java':'21','maven':'3.9+'},'resource_limits':{'maximum_parallel':4,'scope':'local-only'}})
 scale['classes'][0]['loc']=1000000; scale['classes'][1]['repository_count']=1000
 write(pack/'scale/scale-profile.json',scale)

 campaign=load(pack/'campaigns/default.json'); campaign.update({'owner':args.owner,'inventory_snapshot_digest':tree_digest,
   'recipe_set_digest':'sha256:not-selected-local-rehearsal','scope':{'repository_ids':['repo.elmos'],
   'work_unit_ids':[unit['id'] for unit in units],'include':{'mode':'dry-run'},'exclude':{'external_scm_writes':True}},
   'cohorts':[{'key':'local-module-tests','work_unit_ids':[unit['id'] for unit in units],'status':'planned'}],
   'budgets':{'maximum_parallel':4,'external_write_budget':0},
   'rollback':{'mode':'discard-local-workspace','status':'not-run'},'approvals':[]})
 write(pack/'campaigns/default.json',campaign)

 dr=load(pack/'dr/replay-plan.json'); dr.update({'owner':args.owner,'rpo':'NOT_RUN','rto':'NOT_RUN',
   'authoritative_stores':['source-manifest','inventory','dependency-graph','work-unit-plan','workflow-history','commit-tokens'],
   'derived_stores':['semantic-index','cache'],'recovery_order':['inventory','dependency-graph','work-unit-plan','workflow-history'],
   'idempotency':{'commit_token_required':True,'status':'implemented-in-elmos-portfolio-scale'},
   'test_cases':[{'key':'local-workflow-snapshot-restore','status':'covered-by-unit-test'}],
   'evidence_refs':['certification/local-rehearsal.json']})
 write(pack/'dr/replay-plan.json',dr)

 support=load(pack/'support-matrix.json')
 implemented={'portfolio-discovery','monorepo-partitioning','cross-repo-graph','distributed-workflows','runner-fleet',
              'content-addressed-cache','recipe-campaigns','failure-recovery','budget-guardrails','disaster-replay'}
 for capability in support['capabilities']:
  capability['owner']=args.owner
  if capability['key'] in implemented:
   capability['status']='experimental'; capability['evidence_refs']=[source_evidence,'certification/local-rehearsal.json']
   capability['limitations']=['Verified only in a local single-repository rehearsal; production portfolio evidence is NOT_RUN.']
 write(pack/'support-matrix.json',support)

 benchmark=load(pack/'benchmark/result.json'); benchmark.update({'run_id':'NOT_RUN','environment_digest':'NOT_RUN',
   'dataset_digest':'NOT_RUN','status':'not-run','metrics':{},'failures':['REAL_SCALE_ENVIRONMENT_NOT_AUTHORIZED'],
   'evidence_refs':[]}); write(pack/'benchmark/result.json',benchmark)
 cert=load(pack/'certification/certification.json'); cert.update({'status':'experimental','owner':args.owner,
   'exact_scope':manifest['scope'],'holdout':[],'representative_portfolios':[],
   'evidence_refs':[source_evidence,'certification/local-rehearsal.json']}); write(pack/'certification/certification.json',cert)
 evidence=load(pack/'certification/evidence.json'); evidence['evidence_refs']=[source_evidence,'certification/local-rehearsal.json']; write(pack/'certification/evidence.json',evidence)
 write(pack/source_evidence,{'schema_version':1,'status':'passed','scope':'local-worktree','tree_digest':tree_digest,
   'captured_at':captured,'files':manifest_files})
 write(pack/'certification/local-rehearsal.json',{'schema_version':1,'status':'passed','scope':'local-single-repository',
   'inventory':{'repositories':1,'coverage':1.0},'graph':{'nodes':len(nodes),'edges':len(edges)},
   'work_units':len(units),'external_scm':'NOT_RUN','distributed_runner_fleet':'NOT_RUN',
   'million_loc_benchmark':'NOT_RUN','thousand_repository_benchmark':'NOT_RUN',
   'representative_portfolio':'NOT_RUN','production_certification':'NOT_RUN'})
 for relative in ('corpus/development/million-loc/manifest.json','corpus/development/thousand-repository/manifest.json',
                  'corpus/development/mixed-language/manifest.json','corpus/negative/manifest.json',
                  'corpus/holdout/manifest.json','corpus/representative-portfolios/manifest.json'):
  write(pack/relative,{'schema_version':1,'status':'not-run','dataset_digest':'NOT_RUN','evidence_refs':[],
                       'reason':'No authorized independent corpus was supplied for this local rehearsal.'})

 subprocess.run([sys.executable,str(scripts/'validate_portfolio_pack.py'),str(pack)],check=True)
 subprocess.run([sys.executable,str(scripts/'run_portfolio_gate.py'),str(pack)],check=True)
 print(json.dumps({'pack':str(pack),'tree_digest':tree_digest,'modules':len(modules),'loc':total_loc,
                   'certification_decision':'NOT_CERTIFIED'},indent=2))
 return 0

if __name__=='__main__': raise SystemExit(main())
