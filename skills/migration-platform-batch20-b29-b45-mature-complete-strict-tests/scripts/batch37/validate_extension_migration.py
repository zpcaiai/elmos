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
 if not all(o.get(k) is True for k in ['dry_run_passed','checkpointed','reconciliation_passed','rollback_tested','mixed_version_tested']): errors.append('migration evidence incomplete')
 if o.get('secret_values_embedded'): errors.append('secret values embedded')
 if errors:
  print('\n'.join('INVALID: '+x for x in errors),file=sys.stderr); return 1
 print(f'VALID: {p}'); return 0
if __name__=='__main__': raise SystemExit(main())
