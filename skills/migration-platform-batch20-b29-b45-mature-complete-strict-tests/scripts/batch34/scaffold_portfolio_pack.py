#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path
def load(p): return json.loads(p.read_text())
def split(v): return [x.strip() for x in v.split(',') if x.strip()]
def main():
 p=argparse.ArgumentParser(); p.add_argument('--pack-key',required=True); p.add_argument('--scm-provider',required=True); p.add_argument('--organization',required=True); p.add_argument('--tenant-model',default='shared-control-dedicated-execution'); p.add_argument('--region',required=True); p.add_argument('--languages',default='java,csharp,python,typescript'); p.add_argument('--build-systems',default='maven,gradle,msbuild,pip,pnpm'); p.add_argument('--repository-target',type=int,default=1000); p.add_argument('--loc-target',type=int,default=1000000); p.add_argument('--repo-root',default='.'); p.add_argument('--force',action='store_true'); a=p.parse_args()
 if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,95}',a.pack_key): raise SystemExit('invalid --pack-key')
 root=Path(a.repo_root); templates=Path(__file__).resolve().parents[2]/'templates'/'batch34'; pack=root/'portfolio-packs'/a.pack_key
 dirs=['inventory','graph','work-units','index','scheduler','cache','transfer','campaigns','pull-requests','recovery','fairness','budgets','control-tower','scale','benchmark','forecast','dr','corpus/development/million-loc','corpus/development/thousand-repository','corpus/development/mixed-language','corpus/negative','corpus/holdout','corpus/representative-portfolios','certification']
 for d in dirs: (pack/d).mkdir(parents=True,exist_ok=True)
 manifest=load(templates/'portfolio-pack.json'); manifest['pack_key']=a.pack_key; manifest['scope'].update({'tenant_model':a.tenant_model,'scm_sources':[a.scm_provider],'organizations':[a.organization],'regions':[a.region],'languages':split(a.languages),'build_systems':split(a.build_systems),'repository_target':a.repository_target,'loc_target':a.loc_target})
 support=load(templates/'support-matrix.json'); support['pack_key']=a.pack_key
 inventory=load(templates/'portfolio-inventory.json'); inventory['pack_key']=a.pack_key
 work=load(templates/'work-unit-plan.json'); work['pack_key']=a.pack_key
 graph=load(templates/'dependency-graph.json'); graph['pack_key']=a.pack_key
 scale=load(templates/'scale-profile.json'); scale['profile_key']=f'{a.pack_key}-scale-v1'; scale['environment']['regions']=[a.region]; scale['classes'][1]['repository_count']=a.repository_target; scale['classes'][0]['loc']=a.loc_target
 campaign=load(templates/'campaign-plan.json'); campaign['pack_key']=a.pack_key; campaign['campaign_key']=f'{a.pack_key}-default'
 benchmark=load(templates/'benchmark-result.json'); benchmark['pack_key']=a.pack_key; benchmark['profile_key']=scale['profile_key']
 dr=load(templates/'dr-replay-plan.json'); dr['pack_key']=a.pack_key
 evidence=load(templates/'evidence.json'); evidence['pack_key']=a.pack_key
 cert=load(templates/'certification.json'); cert['pack_key']=a.pack_key; cert['exact_scope']=manifest['scope']
 files={pack/'pack.json':manifest,pack/'support-matrix.json':support,pack/'inventory/portfolio.json':inventory,pack/'work-units/plan.json':work,pack/'graph/dependencies.json':graph,pack/'scale/scale-profile.json':scale,pack/'campaigns/default.json':campaign,pack/'benchmark/result.json':benchmark,pack/'dr/replay-plan.json':dr,pack/'certification/evidence.json':evidence,pack/'certification/certification.json':cert}
 for path,data in files.items():
  if not path.exists() or a.force: path.write_text(json.dumps(data,indent=2)+'\n')
 (pack/'certification/gap-inventory.md').write_text('# Gap inventory\n\n- Assign portfolio, platform, security, data, SRE, finance, and migration owners.\n- Capture complete repository inventory and critical dependency evidence.\n- Add work units, index, workflow, fleet, cache, transfer, campaign, PR, fairness, budget, benchmark, forecast, and DR evidence.\n')
 (pack/'README.md').write_text(f'# {a.pack_key}\n\nDirectional exact Batch 34 portfolio-scale pack.\n')
 print(pack); return 0
if __name__=='__main__': raise SystemExit(main())
