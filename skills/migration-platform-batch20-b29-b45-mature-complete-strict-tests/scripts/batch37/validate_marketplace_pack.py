#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load,safe_ref

def main():
 pack=Path(sys.argv[1]); errors=[]
 required=['pack.json','support-matrix.json','sdk/contract.json','extensions/sample/manifest.json','sandbox/policy.json','compatibility/matrix.json','commercial/policy.json','certification/evidence.json','certification/certification.json']
 for rel in required:
  if not (pack/rel).is_file(): errors.append(f'missing {rel}')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 m=load(pack/'pack.json'); cert=load(pack/'certification/certification.json')
 if m.get('pack_key')!=pack.name: errors.append('pack_key must match directory')
 if cert.get('pack_key')!=m.get('pack_key'): errors.append('certification pack_key mismatch')
 if cert.get('exact_scope')!=m.get('scope'): errors.append('certification exact_scope mismatch')
 for group in [m.get('contracts',{}),m.get('corpus',{}),m.get('certification',{})]:
  for ref in group.values():
   if isinstance(ref,str) and not safe_ref(ref): errors.append(f'unsafe ref: {ref}')
 if m.get('owner') in {'','TODO',None}: errors.append('owner missing')
 if m.get('maintenance_owner') in {'','TODO',None}: errors.append('maintenance_owner missing')
 if str(m.get('scope',{}).get('environment_digest','')).endswith('TODO'): errors.append('environment digest placeholder')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 print(f'VALID: {m.get("pack_key")}'); return 0
if __name__=='__main__': raise SystemExit(main())
