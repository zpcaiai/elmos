#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load,safe_ref
ALLOWED={'workspace-read','workspace-write','artifact-read','artifact-write','repository-read','repository-write','network-egress','secret-read','model-call','runner-job','evidence-write','policy-evaluate','billing-meter'}
def main():
 p=Path(sys.argv[1]); m=load(p); errors=[]
 perms=m.get('permissions',[])
 for x in perms:
  if x not in ALLOWED: errors.append(f'unknown permission: {x}')
 if len(perms)!=len(set(perms)): errors.append('duplicate permissions')
 if 'repository-write' in perms and 'repository-read' not in perms: errors.append('repository-write requires repository-read')
 if 'secret-read' in perms and not m.get('data_classification'): errors.append('secret-read requires data classification')
 for ref in m.get('artifacts',{}).values():
  if not safe_ref(ref): errors.append(f'unsafe artifact ref: {ref}')
 if not str(m.get('artifacts',{}).get('package_digest','')).startswith('sha256:'): errors.append('package digest must be sha256')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 print(f'VALID MANIFEST: {m.get("extension_id")}'); return 0
if __name__=='__main__': raise SystemExit(main())
