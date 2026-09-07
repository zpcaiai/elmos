#!/usr/bin/env python3
from __future__ import annotations
import argparse,re
from pathlib import Path
from _common import load,write

def main():
 p=argparse.ArgumentParser(); p.add_argument('--pack-key',required=True); p.add_argument('--migration-route',required=True); p.add_argument('--repository-provider',required=True,choices=['github','gitlab','bitbucket','local']); p.add_argument('--repository-id',required=True); p.add_argument('--risk-tier',default='P0',choices=['P0','P1','P2','P3']); p.add_argument('--source-digest',default='sha256:TODO'); p.add_argument('--target-digest',default='sha256:TODO'); p.add_argument('--environment-digest',default='sha256:TODO'); p.add_argument('--repo-root',default='.'); p.add_argument('--force',action='store_true'); a=p.parse_args()
 if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,95}',a.pack_key): raise SystemExit('invalid --pack-key')
 root=Path(a.repo_root); templates=Path(__file__).resolve().parents[2]/'templates'/'batch36'; pack=root/'developer-experience-packs'/a.pack_key
 dirs=['protocol','extensions','cli','pr-bot','preview','navigation','explainability','quick-fix','conflicts','ownership','local-eval','authoring','review','offline','telemetry','commands','corpus/development','corpus/negative','corpus/holdout','corpus/representative-workflows','certification']
 for d in dirs: (pack/d).mkdir(parents=True,exist_ok=True)
 names=['developer-experience-pack.json','support-matrix.json','ide-protocol.json','intellij-extension.json','visual-studio-extension.json','vscode-extension.json','cli-contract.json','pr-bot-policy.json','navigation-map.json','ownership-policy.json','local-eval-profile.json','recipe-authoring-profile.json','telemetry-policy.json','evidence.json','certification.json']
 data={n:load(templates/n) for n in names}
 scope={'migration_route':a.migration_route,'source_artifact_digest':a.source_digest,'target_artifact_digest':a.target_digest,'repository_provider':a.repository_provider,'repository_id':a.repository_id,'risk_tier':a.risk_tier,'environment_digest':a.environment_digest}
 data['developer-experience-pack.json']['pack_key']=a.pack_key; data['developer-experience-pack.json']['scope']=scope
 data['support-matrix.json']['pack_key']=a.pack_key; data['evidence.json']['pack_key']=a.pack_key; data['certification.json']['pack_key']=a.pack_key; data['certification.json']['exact_scope']=scope; data['navigation-map.json']['map_key']=f'{a.pack_key}-navigation-v1'; data['navigation-map.json']['source_artifact_digest']=a.source_digest; data['navigation-map.json']['target_artifact_digest']=a.target_digest
 mapping={'developer-experience-pack.json':'pack.json','support-matrix.json':'support-matrix.json','ide-protocol.json':'protocol/ide-protocol.json','intellij-extension.json':'extensions/intellij.json','visual-studio-extension.json':'extensions/visual-studio.json','vscode-extension.json':'extensions/vscode.json','cli-contract.json':'cli/contract.json','pr-bot-policy.json':'pr-bot/policy.json','navigation-map.json':'navigation/map.json','ownership-policy.json':'ownership/policy.json','local-eval-profile.json':'local-eval/profile.json','recipe-authoring-profile.json':'authoring/profile.json','telemetry-policy.json':'telemetry/policy.json','evidence.json':'certification/evidence.json','certification.json':'certification/certification.json'}
 for src,dst in mapping.items():
  path=pack/dst
  if not path.exists() or a.force: write(path,data[src])
 for pth,title in [('preview/profile.json','Local preview profile'),('explainability/profile.json','Explainability profile'),('quick-fix/profile.json','Quick-fix profile'),('conflicts/profile.json','Conflict resolution profile'),('review/policy.json','Review policy'),('offline/profile.json','Offline workflow profile')]:
  path=pack/pth
  if not path.exists() or a.force: write(path,{'schema_version':1,'key':a.pack_key+'-'+Path(pth).stem,'title':title,'owner':'TODO','status':'research'})
 (pack/'certification/gap-inventory.md').write_text('# Gap inventory\n\n- Assign product, developer-experience, security, repository, migration-engine, and customer owners.\n- Replace placeholder digests and host version ranges.\n- Add real extension, CLI, SCM, local, offline, privacy, holdout, and representative evidence.\n- Resolve every P0 unknown and zero-tolerance finding.\n')
 (pack/'README.md').write_text(f'# {a.pack_key}\n\nExact Batch 36 Developer Experience Pack.\n')
 print(pack); return 0
if __name__=='__main__': raise SystemExit(main())
