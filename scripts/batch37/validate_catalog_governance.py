from __future__ import annotations
import json,sys
from pathlib import Path
from _common import load,resolve_ref

def main():
 root=Path(sys.argv[1]); errors=[]
 try:
  entry=load(root/'catalog-entry.json') if root.is_dir() else load(root)
  policy=load(root/'ranking-policy.json') if root.is_dir() else None
 except Exception as e: print(f'INVALID: {e}',file=sys.stderr); return 1
 if entry['certification_status'] in {'blocked','revoked'} and (entry['discoverable'] or entry['ranking_eligible']): errors.append('blocked/revoked entry cannot be discoverable or rankable')
 if entry['discoverable'] and not entry['compatibility'].get('product_versions'): errors.append('discoverable entry needs compatibility')
 if policy and policy.get('open_critical_abuse_cases',1)!=0: errors.append('critical abuse cases open')
 if errors: print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {root}'); return 0
if __name__=='__main__': raise SystemExit(main())
