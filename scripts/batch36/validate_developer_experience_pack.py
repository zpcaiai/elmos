#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load

def main():
 import jsonschema
 pack=Path(sys.argv[1]); root=Path(__file__).resolve().parents[2]; errors=[]
 pairs=[('pack.json','developer-experience-pack.schema.json'),('support-matrix.json','developer-support-matrix.schema.json'),('protocol/ide-protocol.json','ide-protocol.schema.json'),('extensions/intellij.json','extension-manifest.schema.json'),('extensions/visual-studio.json','extension-manifest.schema.json'),('extensions/vscode.json','extension-manifest.schema.json'),('cli/contract.json','cli-contract.schema.json'),('pr-bot/policy.json','pr-bot-policy.schema.json'),('navigation/map.json','navigation-map.schema.json'),('ownership/policy.json','ownership-policy.schema.json'),('local-eval/profile.json','local-eval-profile.schema.json'),('authoring/profile.json','recipe-authoring-profile.schema.json'),('telemetry/policy.json','telemetry-policy.schema.json'),('certification/certification.json','developer-experience-certification.schema.json')]
 for rel,schema in pairs:
  try: jsonschema.validate(load(pack/rel),load(root/'schemas/batch36'/schema))
  except Exception as e: errors.append(f'{rel}: {e}')
 try:
  m=load(pack/'pack.json')
  if m.get('owner') in {'','TODO',None}: errors.append('pack owner missing')
  if m.get('maintenance_owner') in {'','TODO',None}: errors.append('maintenance owner missing')
  for k,v in m.get('scope',{}).items():
   if isinstance(v,str) and 'TODO' in v: errors.append(f'scope {k} contains placeholder')
 except Exception: pass
 if errors:
  print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
 print(f'OK: {pack}'); return 0
if __name__=='__main__': raise SystemExit(main())
