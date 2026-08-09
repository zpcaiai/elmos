#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load,resolve_ref

def main():
 pack=Path(sys.argv[1]); r=load(pack/'releases/sample/release.json'); errors=[]
 if r.get('immutable') is not True: errors.append('release must be immutable')
 for k in ['signature_ref','sbom_ref','provenance_ref','certification_ref']:
  ref=r.get(k)
  if not ref or not resolve_ref(pack,ref): errors.append(f'missing release ref: {k}={ref}')
 if not str(r.get('artifact_digest','')).startswith('sha256:'): errors.append('artifact digest must be sha256')
 if r.get('status')=='revoked' and not r.get('revocation'): errors.append('revoked release requires revocation record')
 if errors: print('\n'.join(errors),file=sys.stderr); return 1
 print(f'VALID RELEASE: {r.get("release_id")}'); return 0
if __name__=='__main__': raise SystemExit(main())
