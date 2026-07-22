#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load

def main():
 p=Path(sys.argv[1]); s=load(p); errors=[]
 if s.get('default_action')!='deny': errors.append('default action must deny')
 n=s.get('network',{})
 if n.get('mode')=='allowlist':
  for x in n.get('allowlist',[]):
   if x in {'*','0.0.0.0/0','::/0'} or '*' in x: errors.append(f'wildcard network forbidden: {x}')
 if n.get('deny_metadata_endpoints') is not True: errors.append('metadata endpoints must be denied')
 fs=s.get('filesystem',{})
 for x in fs.get('allowed_paths',[]):
  if x=='/' or '..' in Path(x).parts: errors.append(f'unsafe filesystem path: {x}')
 if fs.get('deny_host_paths') is not True: errors.append('host paths must be denied')
 if s.get('process',{}).get('deny_privileged') is not True: errors.append('privileged process must be denied')
 if s.get('tenant_isolation',{}).get('required') is not True or s.get('tenant_isolation',{}).get('cross_tenant_refs') is not False: errors.append('tenant isolation invalid')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 print(f'VALID SANDBOX: {s.get("policy_id")}'); return 0
if __name__=='__main__': raise SystemExit(main())
