#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load

def main():
 p=load(sys.argv[1]); errors=[]; sec=p.get('security',{})
 if sec.get('arbitrary_shell') is not False: errors.append('arbitrary shell must be false')
 if sec.get('secret_access') not in {'none','reference-only'}: errors.append('secret access must be none or reference-only')
 names=set()
 for m in p.get('methods',[]):
  if m.get('name') in names: errors.append(f'duplicate method {m.get("name")}')
  names.add(m.get('name'))
  if not m.get('cancellable'): errors.append(f'method {m.get("name")} must be cancellable')
  if not m.get('requires_document_version'): errors.append(f'method {m.get("name")} must require document version')
  if not m.get('requires_artifact_digest'): errors.append(f'method {m.get("name")} must require artifact digest')
 if errors: print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
 print('OK: IDE protocol'); return 0
if __name__=='__main__': raise SystemExit(main())
