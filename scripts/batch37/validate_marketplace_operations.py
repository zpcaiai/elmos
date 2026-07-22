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
 if not (o['backup_restore_tested'] and o['dr_tested'] and o['state_reconciled']): errors.append('operations recovery incomplete')
 if o['open_critical_incidents']!=0: errors.append('critical incidents open')
 if errors:
  print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {p}'); return 0
if __name__=='__main__': raise SystemExit(main())
