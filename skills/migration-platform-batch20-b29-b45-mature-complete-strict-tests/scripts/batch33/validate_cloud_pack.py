#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import jsonschema

FILES = {
    'pack.json': 'cloud-pack.schema.json',
    'support-matrix.json': 'cloud-support-matrix.schema.json',
    'source-fingerprint/fingerprint.json': 'source-fingerprint.schema.json',
    'runtime-architecture/contract.json': 'runtime-architecture-contract.schema.json',
    'iac-ir/model.json': 'iac-ir.schema.json',
    'target-profile/profile.json': 'target-profile.schema.json',
    'validation/validation-profile.json': 'validation-profile.schema.json',
    'certification/certification.json': 'cloud-certification.schema.json',
}

PLACEHOLDERS = {'', 'UNSET', 'UNASSIGNED', 'TBD', 'TODO'}

PROHIBITED_COMMAND_PATTERNS = {
    '-auto-approve': 'unattended apply/destroy is prohibited',
    '--auto-approve': 'unattended apply/destroy is prohibited',
    'kubectl apply --validate=false': 'disabling Kubernetes schema validation is prohibited',
    'insecure-skip-tls-verify': 'disabling TLS verification is prohibited',
}

def load(path: Path):
    return json.loads(path.read_text())

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument('pack_dir'); args = p.parse_args()
    pack = Path(args.pack_dir)
    schema_root = Path(__file__).resolve().parents[2] / 'schemas' / 'batch33'
    errors: list[str] = []
    data: dict[str, object] = {}
    for rel, schema_name in FILES.items():
        path = pack / rel
        if not path.is_file():
            errors.append(f'missing {rel}')
            continue
        try:
            obj = load(path); data[rel] = obj
            jsonschema.validate(obj, load(schema_root / schema_name))
        except Exception as exc:
            errors.append(f'{rel}: {exc}')
    manifest = data.get('pack.json', {})
    if isinstance(manifest, dict):
        key = manifest.get('pack_key')
        for rel in ('support-matrix.json', 'source-fingerprint/fingerprint.json', 'runtime-architecture/contract.json', 'iac-ir/model.json', 'certification/certification.json'):
            obj = data.get(rel)
            if isinstance(obj, dict) and obj.get('pack_key') != key:
                errors.append(f'{rel}: pack_key mismatch')
        if manifest.get('owner') in PLACEHOLDERS:
            errors.append('pack owner unset')
        if manifest.get('maintenance_owner') in PLACEHOLDERS:
            errors.append('maintenance owner unset')
        for side in ('source', 'target'):
            tup = manifest.get(side, {})
            for field in ('platform', 'provider', 'account_model'):
                if tup.get(field) in PLACEHOLDERS:
                    errors.append(f'{side}.{field} unset')
            for tool in ('iac_tool', 'runtime'):
                value = tup.get(tool, {})
                if value.get('name') in PLACEHOLDERS or value.get('version') in PLACEHOLDERS:
                    errors.append(f'{side}.{tool} unset')
            if not tup.get('regions') or any(x in PLACEHOLDERS for x in tup.get('regions', [])):
                errors.append(f'{side}.regions unset')
    target = data.get('target-profile/profile.json', {})
    if isinstance(target, dict):
        if target.get('owner') in PLACEHOLDERS:
            errors.append('target profile owner unset')
        backend = target.get('state_backend', {})
        if backend.get('locking') in PLACEHOLDERS:
            errors.append('target state backend locking unset')
        if backend.get('encryption') in PLACEHOLDERS:
            errors.append('target state backend encryption unset')
        serialized = json.dumps(target, sort_keys=True).lower()
        for token, message in PROHIBITED_COMMAND_PATTERNS.items():
            if token.lower() in serialized:
                errors.append(f'target profile contains prohibited command pattern {token!r}: {message}')
        network = target.get('network', {})
        if network.get('default_egress') in {'allow', 'any', '*'}:
            errors.append('target network default egress must not be broadly allowed')
        security = target.get('security', {})
        if security.get('encryption') in {'none', 'disabled', False}:
            errors.append('target encryption must not be disabled')
    validation = data.get('validation/validation-profile.json', {})
    if isinstance(validation, dict) and validation.get('owner') in PLACEHOLDERS:
        errors.append('validation profile owner unset')
    cert = data.get('certification/certification.json', {})
    if isinstance(cert, dict) and cert.get('owner') in PLACEHOLDERS:
        errors.append('certification owner unset')
    if errors:
        print('\n'.join('ERROR: ' + e for e in errors), file=sys.stderr); return 1
    print(f"OK: {manifest.get('pack_key')}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
