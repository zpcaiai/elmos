#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REQUIRED_PACK = ['schema_version','pack_key','version','mode','status','owner','maintenance_owner','source','target','paths','gates']
REQUIRED_DIRS = ['source-fingerprint','contracts','target-profile','recipes','adapters','compatibility','corpus/development','corpus/holdout','corpus/real-repository','certification']
ALLOWED_PACK_STATUS = {'research','experimental','limited','certified','deprecated','blocked'}
ALLOWED_CAP_STATUS = {'certified','supported','conditional','experimental','detected-only','blocked'}
ALLOWED_MODES = {'migration','upgrade','modernization','coexistence'}


def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise ValueError(f'{path}: {exc}') from exc


def side_errors(label: str, side: dict) -> list[str]:
    errors = []
    for key in ['framework','framework_versions','runtime','runtime_versions']:
        if not side.get(key):
            errors.append(f'{label} missing/non-empty key: {key}')
    for field in ['framework_versions','runtime_versions']:
        for version in side.get(field, []):
            if str(version).strip().lower() in {'latest','*','x'}:
                errors.append(f'{label} uses floating {field}: {version}')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('pack_dir')
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    errors: list[str] = []
    if not pack.is_dir():
        errors.append(f'missing pack dir: {pack}')
    for rel in REQUIRED_DIRS:
        if not (pack/rel).exists():
            errors.append(f'missing: {pack/rel}')
    manifest = {}
    try:
        manifest = load(pack/'pack.json')
        for key in REQUIRED_PACK:
            if key not in manifest:
                errors.append(f'pack.json missing key: {key}')
        if manifest.get('status') not in ALLOWED_PACK_STATUS:
            errors.append('invalid pack status')
        if manifest.get('mode') not in ALLOWED_MODES:
            errors.append('invalid pack mode')
        if manifest.get('owner') in {'','UNASSIGNED',None}:
            errors.append('pack owner is unassigned')
        if manifest.get('maintenance_owner') in {'','UNASSIGNED',None}:
            errors.append('maintenance owner is unassigned')
        errors.extend(side_errors('source', manifest.get('source', {})))
        errors.extend(side_errors('target', manifest.get('target', {})))
    except Exception as exc:
        errors.append(str(exc))
    try:
        support = load(pack/'support-matrix.json')
        if support.get('pack_key') != manifest.get('pack_key'):
            errors.append('support matrix pack_key mismatch')
        ids = set()
        for capability in support.get('capabilities', []):
            cid = capability.get('id')
            if cid in ids:
                errors.append(f'duplicate capability id: {cid}')
            ids.add(cid)
            status = capability.get('status')
            if status not in ALLOWED_CAP_STATUS:
                errors.append(f'invalid capability status: {cid}')
            if status == 'certified' and not capability.get('evidence_refs'):
                errors.append(f'certified capability lacks evidence: {cid}')
            if status in {'conditional','blocked'} and not capability.get('reason'):
                errors.append(f'conditional/blocked capability lacks reason: {cid}')
    except Exception as exc:
        errors.append(str(exc))
    try:
        profile = load(pack/'target-profile'/'profile.json')
        for key in ['profile_key','version','owner','framework','framework_versions','runtime','runtime_versions','architecture_style','providers','build','startup']:
            if not profile.get(key):
                errors.append(f'target profile missing/non-empty key: {key}')
        if profile.get('owner') in {'','UNASSIGNED',None}:
            errors.append('target profile owner is unassigned')
    except Exception as exc:
        errors.append(str(exc))
    for path in [
        pack/'version-matrix.json',
        pack/'source-fingerprint'/'manifest.json',
        pack/'source-fingerprint'/'evidence.json',
        pack/'compatibility'/'manifest.json',
        pack/'certification'/'evidence.json',
        pack/'certification'/'certification.json',
    ]:
        try:
            load(path)
        except Exception as exc:
            errors.append(str(exc))
    if errors:
        print('\n'.join(f'ERROR: {item}' for item in errors), file=sys.stderr)
        return 1
    print(f'OK: {pack}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
