#!/usr/bin/env python3
from __future__ import annotations
import argparse,re,shutil
from pathlib import Path
from _common import load,write

def main():
 p=argparse.ArgumentParser(); p.add_argument('--pack-key',required=True); p.add_argument('--migration-route',required=True); p.add_argument('--workload-key',required=True); p.add_argument('--risk-tier',default='P0',choices=['P0','P1','P2','P3']); p.add_argument('--source-digest',default='sha256:TODO'); p.add_argument('--target-digest',default='sha256:TODO'); p.add_argument('--environment-digest',default='sha256:TODO'); p.add_argument('--repo-root',default='.'); p.add_argument('--force',action='store_true'); a=p.parse_args()
 if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,95}',a.pack_key): raise SystemExit('invalid --pack-key')
 root=Path(a.repo_root); templates=Path(__file__).resolve().parents[2]/'templates'/'batch35'; pack=root/'verification-packs'/a.pack_key
 dirs=['properties','metamorphic','mutation','fuzz','symbolic','models','state-machines','contracts','invariants','security','concurrency','queries','numeric','solver','oracles','coverage','counterexamples','assurance','corpus/development','corpus/negative','corpus/holdout','corpus/representative-workloads','certification']
 for d in dirs: (pack/d).mkdir(parents=True,exist_ok=True)
 data={fn:load(templates/fn) for fn in ['verification-pack.json','support-matrix.json','validation-profile.json','oracle-registry.json','property-spec.json','metamorphic-relation.json','mutation-campaign.json','fuzz-campaign.json','model-spec.json','solver-proof.json','counterexample.json','assurance-case.json','evidence.json','certification.json']}
 data['verification-pack.json']['pack_key']=a.pack_key; data['verification-pack.json']['scope'].update({'migration_route':a.migration_route,'source_artifact_digest':a.source_digest,'target_artifact_digest':a.target_digest,'workload_key':a.workload_key,'risk_tier':a.risk_tier,'environment_digest':a.environment_digest})
 data['support-matrix.json']['pack_key']=a.pack_key; data['validation-profile.json']['profile_key']=f'{a.pack_key}-profile-v1'; data['validation-profile.json']['risk_tier']=a.risk_tier; data['oracle-registry.json']['pack_key']=a.pack_key; data['evidence.json']['pack_key']=a.pack_key; data['certification.json']['pack_key']=a.pack_key; data['certification.json']['exact_scope']=data['verification-pack.json']['scope']; data['assurance-case.json']['case_key']=f'{a.pack_key}-assurance-v1'
 mapping={'verification-pack.json':'pack.json','support-matrix.json':'support-matrix.json','validation-profile.json':'validation-profile.json','oracle-registry.json':'oracle-registry.json','property-spec.json':'properties/sample.json','metamorphic-relation.json':'metamorphic/sample.json','mutation-campaign.json':'mutation/campaign.json','fuzz-campaign.json':'fuzz/campaign.json','model-spec.json':'models/model.json','solver-proof.json':'solver/proof.json','counterexample.json':'counterexamples/sample.json','assurance-case.json':'assurance/assurance-case.json','evidence.json':'certification/evidence.json','certification.json':'certification/certification.json'}
 for src,dst in mapping.items():
  path=pack/dst
  if not path.exists() or a.force: write(path,data[src])
 (pack/'certification/gap-inventory.md').write_text('# Gap inventory\n\n- Assign business, engineering, security, data, operations, and verification owners.\n- Replace placeholder digests and versions.\n- Add executable negative, holdout, and representative evidence.\n- Resolve every P0 unknown and oracle conflict.\n')
 (pack/'README.md').write_text(f'# {a.pack_key}\n\nExact Batch 35 advanced verification pack.\n')
 print(pack); return 0
if __name__=='__main__': raise SystemExit(main())
