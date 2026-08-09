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
 active=[k for k in o['signing_keys'] if k['status'] in {'active','overlap'}]
 if o['status']=='active' and not active: errors.append('active publisher needs active signing key')
 if o['open_critical_findings']!=0: errors.append('critical publisher findings open')
 if not any(m['status']=='active' for m in o['maintainers']): errors.append('no active maintainer')
 if errors:
  print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {p}'); return 0
if __name__=='__main__': raise SystemExit(main())
