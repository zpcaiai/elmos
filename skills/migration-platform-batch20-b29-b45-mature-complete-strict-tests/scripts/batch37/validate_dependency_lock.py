from __future__ import annotations
import json,sys
from pathlib import Path
from _common import load,resolve_ref

def main():
 p=Path(sys.argv[1]); errors=[]
 try:
  o=load(p)
 except Exception as e:
  print(f'INVALID: {e}',file=sys.stderr); return 1
 nodes={(x['extension_id'],x['version']):x for x in o['nodes']}
 ids=[(x['extension_id'],x['version']) for x in o['nodes']]
 errors += ['duplicate dependency nodes'] if len(ids)!=len(set(ids)) else []
 errors += ['dependency cycles must be empty'] if o.get('cycles') else []
 errors += ['lock digest must be sha256'] if not o.get('lock_digest','').startswith('sha256:') else []
 for x in o['nodes']:
  if x['version'] in {'latest','*'} or '*' in x['version']: errors.append('floating dependency version')
  if x['status'] in {'revoked','quarantined'} and x['extension_id'] not in o['revocation_propagation'].get('blocked_nodes',[]): errors.append('revoked/quarantined dependency not propagated')
 for e in o['edges']:
  if not any(n[0]==e['from'] for n in nodes): errors.append('edge source missing')
  if not any(n[0]==e['to'] for n in nodes): errors.append('edge target missing')
  if e['constraint'] in {'latest','*'}: errors.append('floating edge constraint')
 if errors:
  print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {p}'); return 0
if __name__=='__main__': raise SystemExit(main())
