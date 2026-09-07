#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from _common import load,write

def main():
 p=argparse.ArgumentParser(); p.add_argument('pack'); p.add_argument('--force',action='store_true'); a=p.parse_args(); pack=Path(a.pack); root=Path(__file__).resolve().parents[2]; t=root/'templates/batch37'
 if not (pack/'pack.json').is_file(): raise SystemExit('pack.json missing')
 dirs=['dependencies','runtime','catalog','migrations','continuity','legal-support','private-marketplace','offline-mirror','operations','lifecycle','corpus/closure-holdout','corpus/representative-lifecycle']
 for d in dirs: (pack/d).mkdir(parents=True,exist_ok=True)
 mapping={'dependency-lock.json':'dependencies/lock.json','runtime-health.json':'runtime/health.json','catalog-entry.json':'catalog/catalog-entry.json','ranking-policy.json':'catalog/ranking-policy.json','publisher-lifecycle.json':'publishers/lifecycle.json','recertification-policy.json':'certification/recertification-policy.json','extension-migration.json':'migrations/extension-migration.json','continuity-plan.json':'continuity/revocation-plan.json','legal-support.json':'legal-support/policy.json','private-marketplace.json':'private-marketplace/policy.json','offline-mirror.json':'offline-mirror/policy.json','marketplace-operations.json':'operations/operations-policy.json','commercial-settlement.json':'commercial/settlement.json','eol-policy.json':'lifecycle/eol-policy.json','closure-certification.json':'certification/closure-certification.json'}
 for src,dst in mapping.items():
  pth=pack/dst
  if not pth.exists() or a.force: write(pth,load(t/src))
 m=load(pack/'pack.json'); tmpl=load(t/'marketplace-pack.json'); m['schema_version']=2; m['contracts'].update({k:v for k,v in tmpl['contracts'].items() if k not in {'extension_manifest','sandbox_policy','publisher_profile','compatibility_matrix','commercial_policy'}}); m['corpus'].update({'closure_holdout':'corpus/closure-holdout','representative_lifecycle':'corpus/representative-lifecycle'}); m['certification'].update({'closure_certification_path':'certification/closure-certification.json','closure_result_path':'certification/closure-gate-result.json'}); m['tags']=sorted(set(m.get('tags',[])+['batch37','closure-complete'])); write(pack/'pack.json',m)
 print(pack); return 0
if __name__=='__main__': raise SystemExit(main())
