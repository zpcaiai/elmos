#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REQUIRED_ROUTE = ['schema_version','route_key','version','status','owner','source','target','paths','gates']
REQUIRED_DIRS = ['lowering','mappings','compat-runtime','corpus/development','corpus/holdout','corpus/real-repository','certification']
ALLOWED_ROUTE_STATUS = {'research','experimental','limited','certified','deprecated','blocked'}
ALLOWED_CAP_STATUS = {'certified','supported','conditional','experimental','detected-only','blocked'}

def load(path: Path):
    try: return json.loads(path.read_text())
    except Exception as e: raise ValueError(f'{path}: {e}')

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('route_dir'); a=p.parse_args()
    route=Path(a.route_dir)
    errors=[]
    if not route.is_dir(): errors.append(f'missing route dir: {route}')
    for d in REQUIRED_DIRS:
        if not (route/d).exists(): errors.append(f'missing: {route/d}')
    try:
        manifest=load(route/'route.json')
        for k in REQUIRED_ROUTE:
            if k not in manifest: errors.append(f'route.json missing key: {k}')
        if manifest.get('status') not in ALLOWED_ROUTE_STATUS: errors.append('invalid route status')
        if manifest.get('source',{}).get('language') == manifest.get('target',{}).get('language'): errors.append('source and target must differ')
        if not manifest.get('source',{}).get('versions'): errors.append('source versions are empty')
        if not manifest.get('target',{}).get('versions'): errors.append('target versions are empty')
        if manifest.get('owner') in {'','UNASSIGNED',None}: errors.append('route owner is unassigned')
    except Exception as e: errors.append(str(e))
    try:
        support=load(route/'support-matrix.json')
        if support.get('route_key') != manifest.get('route_key'): errors.append('support matrix route_key mismatch')
        for cap in support.get('capabilities',[]):
            if cap.get('status') not in ALLOWED_CAP_STATUS: errors.append(f"invalid capability status: {cap.get('id')}")
            if cap.get('status') == 'certified' and not cap.get('evidence_refs'): errors.append(f"certified capability lacks evidence: {cap.get('id')}")
            if cap.get('status') in {'conditional','blocked'} and not cap.get('reason'): errors.append(f"conditional/blocked capability lacks reason: {cap.get('id')}")
    except Exception as e: errors.append(str(e))
    for f in [route/'compat-runtime'/'manifest.json', route/'certification'/'evidence.json', route/'certification'/'certification.json']:
        try: load(f)
        except Exception as e: errors.append(str(e))
    if errors:
        print('\n'.join(f'ERROR: {x}' for x in errors), file=sys.stderr)
        return 1
    print(f'OK: {route}')
    return 0
if __name__=='__main__': raise SystemExit(main())
