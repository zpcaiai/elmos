#!/usr/bin/env python3
from __future__ import annotations
import argparse,re
from pathlib import Path
from _common import load,write

def main():
 p=argparse.ArgumentParser(); p.add_argument('--pack-key',required=True); p.add_argument('--product-version',required=True); p.add_argument('--protocol-version',default='1.0.0'); p.add_argument('--edition',default='enterprise'); p.add_argument('--risk-tier',default='P0',choices=['P0','P1','P2','P3']); p.add_argument('--environment-digest',default='sha256:TODO'); p.add_argument('--publisher-id',default='sample-publisher'); p.add_argument('--extension-id',default='sample.publisher.extension'); p.add_argument('--extension-kind',default='transformation-recipe'); p.add_argument('--repo-root',default='.'); p.add_argument('--force',action='store_true'); a=p.parse_args()
 if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,95}',a.pack_key): raise SystemExit('invalid --pack-key')
 root=Path(a.repo_root); t=Path(__file__).resolve().parents[2]/'templates'/'batch37'; pack=root/'marketplace-packs'/a.pack_key
 dirs=['sdk','extensions/sample','sandbox','publishers','compatibility','releases/sample','certification','commercial','installations','revocations','billing','corpus/development','corpus/negative','corpus/holdout','corpus/representative-extensions','dependencies','runtime','catalog','migrations','continuity','legal-support','private-marketplace','offline-mirror','operations','lifecycle','corpus/closure-holdout','corpus/representative-lifecycle']
 for d in dirs: (pack/d).mkdir(parents=True,exist_ok=True)
 names=['marketplace-pack.json','extension-manifest.json','sdk-contract.json','sandbox-policy.json','publisher-profile.json','compatibility-matrix.json','release-record.json','commercial-policy.json','support-matrix.json','evidence.json','certification.json']
 data={n:load(t/n) for n in names}; scope={'product_version':a.product_version,'protocol_version':a.protocol_version,'edition':a.edition,'risk_tier':a.risk_tier,'environment_digest':a.environment_digest}
 data['marketplace-pack.json'].update({'pack_key':a.pack_key,'scope':scope}); data['support-matrix.json']['pack_key']=a.pack_key; data['evidence.json']['pack_key']=a.pack_key; data['certification.json'].update({'pack_key':a.pack_key,'exact_scope':scope})
 m=data['extension-manifest.json']; m.update({'extension_id':a.extension_id,'publisher_id':a.publisher_id,'kind':a.extension_kind}); data['publisher-profile.json']['publisher_id']=a.publisher_id; r=data['release-record.json']; r.update({'release_id':f'{a.extension_id}@{r["version"]}','extension_id':a.extension_id})
 mapping={'marketplace-pack.json':'pack.json','support-matrix.json':'support-matrix.json','extension-manifest.json':'extensions/sample/manifest.json','sdk-contract.json':'sdk/contract.json','sandbox-policy.json':'sandbox/policy.json','publisher-profile.json':f'publishers/{a.publisher_id}.json','compatibility-matrix.json':'compatibility/matrix.json','release-record.json':'releases/sample/release.json','commercial-policy.json':'commercial/policy.json','evidence.json':'certification/evidence.json','certification.json':'certification/certification.json'}
 data['marketplace-pack.json']['contracts']['publisher_profile']=f'publishers/{a.publisher_id}.json'
 for src,dst in mapping.items():
  path=pack/dst
  if not path.exists() or a.force: write(path,data[src])
 for rel,body in [('releases/sample/package.tgz','sample package'),('releases/sample/signature.sig','TODO signature'),('releases/sample/sbom.json','{}'),('releases/sample/provenance.json','{}')]:
  pth=pack/rel
  if not pth.exists() or a.force: pth.write_text(body+'\n')
 (pack/'certification/gap-inventory.md').write_text('# Gap inventory\n\n- Assign product, SDK, security, marketplace, legal, finance, support, and customer-data owners.\n- Replace placeholder product versions, digests, publisher facts, signatures, SBOM, provenance, and certification evidence.\n- Add real negative, holdout, representative extension, installation, rollback, revocation, and billing evidence.\n- Resolve every P0 unknown and zero-tolerance finding.\n')
 
 # Add complete closure contracts and templates.
 closure_mapping={'dependency-lock.json':'dependencies/lock.json','runtime-health.json':'runtime/health.json','catalog-entry.json':'catalog/catalog-entry.json','ranking-policy.json':'catalog/ranking-policy.json','publisher-lifecycle.json':'publishers/lifecycle.json','recertification-policy.json':'certification/recertification-policy.json','extension-migration.json':'migrations/extension-migration.json','continuity-plan.json':'continuity/revocation-plan.json','legal-support.json':'legal-support/policy.json','private-marketplace.json':'private-marketplace/policy.json','offline-mirror.json':'offline-mirror/policy.json','marketplace-operations.json':'operations/operations-policy.json','commercial-settlement.json':'commercial/settlement.json','eol-policy.json':'lifecycle/eol-policy.json','closure-certification.json':'certification/closure-certification.json'}
 for src,dst in closure_mapping.items():
  pth=pack/dst
  if not pth.exists() or a.force: write(pth,load(t/src))
 full=load(t/'marketplace-pack.json'); current=load(pack/'pack.json'); current['schema_version']=2; current['contracts'].update({k:v for k,v in full['contracts'].items() if k not in {'extension_manifest','sandbox_policy','publisher_profile','compatibility_matrix','commercial_policy'}}); current['corpus'].update({'closure_holdout':'corpus/closure-holdout','representative_lifecycle':'corpus/representative-lifecycle'}); current['certification'].update({'closure_certification_path':'certification/closure-certification.json','closure_result_path':'certification/closure-gate-result.json'}); current['tags']=sorted(set(current.get('tags',[])+['batch37','closure-complete'])); write(pack/'pack.json',current)
 (pack/'README.md').write_text(f'# {a.pack_key}\n\nExact Batch 37 complete Marketplace Pack.\n'); print(pack); return 0
if __name__=='__main__': raise SystemExit(main())
