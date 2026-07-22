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
 required={'product-version','sdk-version','dependency','permission','cve'}
 if not required.issubset(set(o['triggers'])): errors.append('required recertification triggers missing')
 if o['overdue'] or not o['current']: errors.append('certification stale or overdue')
 if o['open_critical_findings']!=0: errors.append('critical recertification findings open')
 if errors:
  print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {p}'); return 0
if __name__=='__main__': raise SystemExit(main())
