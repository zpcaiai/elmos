#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,sys
from pathlib import Path
from _common import load,real_files
try:
 import jsonschema
except Exception:
 jsonschema=None
PAIRS=[('pack.json','verification-pack.schema.json'),('support-matrix.json','verification-support-matrix.schema.json'),('validation-profile.json','validation-profile.schema.json'),('oracle-registry.json','oracle-registry.schema.json'),('properties/sample.json','property-spec.schema.json'),('metamorphic/sample.json','metamorphic-relation.schema.json'),('mutation/campaign.json','mutation-campaign.schema.json'),('fuzz/campaign.json','fuzz-campaign.schema.json'),('models/model.json','model-spec.schema.json'),('solver/proof.json','solver-proof.schema.json'),('counterexamples/sample.json','counterexample.schema.json'),('assurance/assurance-case.json','assurance-case.schema.json'),('certification/certification.json','verification-certification.schema.json')]
def main():
 pack=Path(sys.argv[1]); schemas=Path(__file__).resolve().parents[2]/'schemas/batch35'; errors=[]
 for rel,schema in PAIRS:
  p=pack/rel
  if not p.is_file(): errors.append(f'missing {rel}'); continue
  try:
   data=load(p)
   if jsonschema: jsonschema.validate(data,load(schemas/schema))
  except Exception as e: errors.append(f'{rel}: {e}')
 if (pack/'oracle-registry.json').is_file() and subprocess.run([sys.executable,str(Path(__file__).with_name('validate_oracle_registry.py')),str(pack/'oracle-registry.json')]).returncode: errors.append('oracle registry validation failed')
 if (pack/'models/model.json').is_file() and subprocess.run([sys.executable,str(Path(__file__).with_name('validate_model_spec.py')),str(pack/'models/model.json')]).returncode: errors.append('model spec validation failed')
 p=load(pack/'pack.json') if (pack/'pack.json').is_file() else {}
 for key in ('owner','maintenance_owner'):
  if p.get(key) in (None,'','TODO'): errors.append(f'pack {key} is not assigned')
 for key,val in p.get('scope',{}).items():
  if isinstance(val,str) and 'TODO' in val: errors.append(f'scope {key} is placeholder')
 if errors: print('\n'.join('ERROR: '+x for x in errors),file=sys.stderr); return 1
 print(f'OK: verification pack {p.get("pack_key")}'); return 0
if __name__=='__main__': raise SystemExit(main())
