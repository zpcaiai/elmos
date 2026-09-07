#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REQUIRED_DIRS=['source-fingerprint','source-snapshots','canonical-ir','target-profile','transformations','compatibility','migration','corpus/development','corpus/holdout','corpus/representative-workloads','certification']
PACK_STATUS={'research','experimental','limited','certified','deprecated','blocked'}
CAP_STATUS={'certified','supported','conditional','experimental','detected-only','blocked'}
MODES={'assessment','migration','upgrade','modernization','coexistence'}
BAD={'','UNSET','UNASSIGNED','latest','*','x',None}

def load(path:Path):
    try:return json.loads(path.read_text())
    except Exception as exc: raise ValueError(f'{path}: {exc}') from exc

def side_errors(label:str, side:dict)->list[str]:
    errors=[]
    for k in ['engine','versions','edition','dialect','driver_versions','charset','collation','timezone','extensions']:
        if k not in side: errors.append(f'{label} missing key: {k}')
    for k in ['engine','edition','dialect','charset','collation','timezone']:
        if side.get(k) in BAD: errors.append(f'{label} has unset {k}')
    for field in ['versions','driver_versions']:
        vals=side.get(field,[])
        if not vals: errors.append(f'{label} {field} empty')
        for v in vals:
            if str(v).strip().lower() in {'latest','*','x','unset',''}: errors.append(f'{label} uses floating/unset {field}: {v}')
    return errors

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('pack_dir'); a=p.parse_args(); pack=Path(a.pack_dir); errors=[]
    if not pack.is_dir(): errors.append(f'missing pack dir: {pack}')
    for rel in REQUIRED_DIRS:
        if not (pack/rel).exists(): errors.append(f'missing: {pack/rel}')
    manifest={}
    try:
        manifest=load(pack/'pack.json')
        for k in ['schema_version','pack_key','version','mode','status','owner','maintenance_owner','data_owner','source','target','scope','paths','gates']:
            if k not in manifest: errors.append(f'pack.json missing key: {k}')
        if manifest.get('status') not in PACK_STATUS: errors.append('invalid pack status')
        if manifest.get('mode') not in MODES: errors.append('invalid pack mode')
        for k in ['owner','maintenance_owner','data_owner']:
            if manifest.get(k) in BAD: errors.append(f'{k} is unassigned')
        errors += side_errors('source',manifest.get('source',{})); errors += side_errors('target',manifest.get('target',{}))
    except Exception as exc: errors.append(str(exc))
    try:
        support=load(pack/'support-matrix.json')
        if support.get('pack_key') != manifest.get('pack_key'): errors.append('support matrix pack_key mismatch')
        ids=set()
        for cap in support.get('capabilities',[]):
            cid=cap.get('id')
            if cid in ids: errors.append(f'duplicate capability id: {cid}')
            ids.add(cid)
            status=cap.get('status')
            if status not in CAP_STATUS: errors.append(f'invalid capability status: {cid}')
            if cap.get('owner') in BAD: errors.append(f'capability owner unassigned: {cid}')
            if status in {'certified','supported'} and not cap.get('evidence_refs'): errors.append(f'{status} capability lacks evidence: {cid}')
            if status in {'conditional','blocked'} and not cap.get('reason'): errors.append(f'{status} capability lacks reason: {cid}')
    except Exception as exc: errors.append(str(exc))
    try:
        profile=load(pack/'target-profile'/'profile.json')
        for k in ['profile_key','version','owner','engine','versions','edition','dialect','driver_versions','charset','collation','timezone','provision','health_check','security','migration']:
            if not profile.get(k): errors.append(f'target profile missing/non-empty key: {k}')
        if profile.get('owner') in BAD: errors.append('target profile owner unassigned')
        errors += side_errors('target profile',profile)
    except Exception as exc: errors.append(str(exc))
    try:
        plan=load(pack/'migration'/'data-migration-plan.json')
        if plan.get('owner') in BAD: errors.append('data migration plan owner unassigned')
        for k in ['strategy','source','target','backfill','cdc','authority','reconciliation','rollback','privacy']:
            if k not in plan: errors.append(f'data migration plan missing {k}')
    except Exception as exc: errors.append(str(exc))
    for path in [pack/'route-matrix.json',pack/'source-fingerprint'/'manifest.json',pack/'source-fingerprint'/'evidence.json',pack/'canonical-ir'/'model.json',pack/'compatibility'/'manifest.json',pack/'certification'/'evidence.json',pack/'certification'/'certification.json']:
        try: load(path)
        except Exception as exc: errors.append(str(exc))
    if errors:
        print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
    print(f'OK: {pack}'); return 0
if __name__=='__main__': raise SystemExit(main())
