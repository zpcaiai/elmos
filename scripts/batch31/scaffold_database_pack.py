#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')
MODES = ('assessment','migration','upgrade','modernization','coexistence')

def load(path: Path): return json.loads(path.read_text())

def main() -> int:
    p=argparse.ArgumentParser(description='Scaffold an exact, directional Batch 31 database pack.')
    p.add_argument('--source-engine',required=True); p.add_argument('--target-engine',required=True)
    p.add_argument('--source-version',required=True); p.add_argument('--target-version',required=True)
    p.add_argument('--source-edition',required=True); p.add_argument('--target-edition',required=True)
    p.add_argument('--source-dialect'); p.add_argument('--target-dialect')
    p.add_argument('--mode',choices=MODES,default='migration'); p.add_argument('--pack-key')
    p.add_argument('--repo-root',default='.'); p.add_argument('--force',action='store_true')
    a=p.parse_args()
    for value in [a.source_engine,a.target_engine]:
        if not SLUG.fullmatch(value): p.error(f'invalid engine slug: {value!r}')
    key=a.pack_key or f'{a.source_engine}-to-{a.target_engine}'
    if not SLUG.fullmatch(key): p.error(f'invalid pack key: {key!r}')
    if a.source_version.lower() in {'latest','*','x'} or a.target_version.lower() in {'latest','*','x'}: p.error('exact versions required')
    root=Path(a.repo_root).resolve(); pack=root/'database-packs'/key
    if pack.exists() and not a.force: print(f'EXISTS: {pack}'); return 0
    dirs=['source-fingerprint/static','source-fingerprint/runtime','source-snapshots/ddl','source-snapshots/catalogs','source-snapshots/stats','source-snapshots/plans','canonical-ir/schema','canonical-ir/queries','canonical-ir/routines','canonical-ir/pipelines','target-profile/ddl','target-profile/config','target-profile/dependency-locks','transformations/schema','transformations/query','transformations/routine','transformations/pipeline','compatibility','migration/schema','migration/backfill','migration/cdc','migration/reconciliation','migration/cutover','corpus/development/schema','corpus/development/queries','corpus/development/routines','corpus/development/data','corpus/development/pipelines','corpus/development/negative','corpus/holdout','corpus/representative-workloads','certification']
    for d in dirs: (pack/d).mkdir(parents=True,exist_ok=True)
    tr=root/'templates'/'batch31'
    if not tr.exists(): tr=Path(__file__).resolve().parents[2]/'templates'/'batch31'
    manifest=load(tr/'database-pack.json'); manifest['pack_key']=key; manifest['mode']=a.mode
    manifest['source'].update({'engine':a.source_engine,'versions':[a.source_version],'edition':a.source_edition,'dialect':a.source_dialect or a.source_engine,'driver_versions':['UNSET']})
    manifest['target'].update({'engine':a.target_engine,'versions':[a.target_version],'edition':a.target_edition,'dialect':a.target_dialect or a.target_engine,'driver_versions':['UNSET']})
    support=load(tr/'support-matrix.json'); support['pack_key']=key
    fp=load(tr/'workload-fingerprint.json'); fp['pack_key']=key
    ir=load(tr/'canonical-db-ir.json'); ir['pack_key']=key
    profile=load(tr/'target-profile.json'); profile.update({'profile_key':f'{key}-target','engine':a.target_engine,'versions':[a.target_version],'edition':a.target_edition,'dialect':a.target_dialect or a.target_engine,'driver_versions':['UNSET']})
    plan=load(tr/'data-migration-plan.json'); plan['pack_key']=key
    evidence=load(tr/'evidence.json'); evidence['pack_key']=key
    cert=load(tr/'certification.json'); cert['pack_key']=key; cert['exact_tuple']={'source':manifest['source'],'target':manifest['target']}
    route={'schema_version':1,'pack_key':key,'tuples':[{'source_engine':a.source_engine,'source_version':a.source_version,'source_edition':a.source_edition,'target_engine':a.target_engine,'target_version':a.target_version,'target_edition':a.target_edition,'status':'research','evidence_refs':[]}], 'recertification_triggers':[]}
    files={pack/'pack.json':manifest,pack/'support-matrix.json':support,pack/'route-matrix.json':route,pack/'source-fingerprint'/'manifest.json':fp,pack/'source-fingerprint'/'evidence.json':{'schema_version':1,'pack_key':key,'runs':[],'coverage':0,'evidence_refs':[]},pack/'canonical-ir'/'model.json':ir,pack/'target-profile'/'profile.json':profile,pack/'compatibility'/'manifest.json':{'schema_version':1,'pack_key':key,'components':[],'budget':{'max_components':5,'prohibited_domains':['money','security','transaction-core'],'max_emulated_object_ratio':0.10}},pack/'migration'/'data-migration-plan.json':plan,pack/'certification'/'evidence.json':evidence,pack/'certification'/'certification.json':cert}
    for path,data in files.items():
        if not path.exists() or a.force: path.write_text(json.dumps(data,indent=2)+'\n')
    (pack/'certification'/'gap-inventory.md').write_text('# Gap inventory\n\n- Assign owners and exact driver/configuration facts.\n- Add source/target execution, holdout, representative workload, and reconciliation evidence.\n')
    (pack/'README.md').write_text(f'# {key}\n\nDirectional, exact Batch 31 database modernization pack.\n')
    print(pack); return 0

if __name__=='__main__': raise SystemExit(main())
