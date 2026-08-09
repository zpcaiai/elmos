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
 if abs(float(o['reconciliation_difference']))>1e-9: errors.append('settlement difference non-zero')
 if o['fraud_findings_open']!=0: errors.append('fraud findings open')
 if len(set(o['approvals']))<2: errors.append('separation of duties approvals missing')
 if errors:
  print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {p}'); return 0
if __name__=='__main__': raise SystemExit(main())
