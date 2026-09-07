#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load, safe_ref

STATIC_FILES = [
    ('pack.json', 'marketplace-pack.schema.json'),
    ('support-matrix.json', 'marketplace-support-matrix.schema.json'),
    ('extensions/sample/manifest.json', 'extension-manifest.schema.json'),
    ('sdk/contract.json', 'sdk-contract.schema.json'),
    ('sandbox/policy.json', 'sandbox-policy.schema.json'),
    ('compatibility/matrix.json', 'compatibility-matrix.schema.json'),
    ('releases/sample/release.json', 'release-record.schema.json'),
    ('commercial/policy.json', 'commercial-policy.schema.json'),
    ('certification/certification.json', 'marketplace-certification.schema.json'),
    ('dependencies/lock.json', 'dependency-lock.schema.json'),
    ('runtime/health.json', 'runtime-health.schema.json'),
    ('catalog/catalog-entry.json', 'catalog-entry.schema.json'),
    ('catalog/ranking-policy.json', 'ranking-policy.schema.json'),
    ('publishers/lifecycle.json', 'publisher-lifecycle.schema.json'),
    ('certification/recertification-policy.json', 'recertification-policy.schema.json'),
    ('migrations/extension-migration.json', 'extension-migration.schema.json'),
    ('continuity/revocation-plan.json', 'continuity-plan.schema.json'),
    ('legal-support/policy.json', 'legal-support.schema.json'),
    ('private-marketplace/policy.json', 'private-marketplace.schema.json'),
    ('offline-mirror/policy.json', 'offline-mirror.schema.json'),
    ('operations/operations-policy.json', 'marketplace-operations.schema.json'),
    ('commercial/settlement.json', 'commercial-settlement.schema.json'),
    ('lifecycle/eol-policy.json', 'eol-policy.schema.json'),
    ('certification/closure-certification.json', 'closure-certification.schema.json'),
]


def main() -> int:
    pack = Path(sys.argv[1])
    schemas = Path(__file__).resolve().parents[2] / 'schemas' / 'batch37'
    errors: list[str] = []
    try:
        import jsonschema
        manifest = load(pack / 'pack.json')
    except Exception as exc:
        print(f'INVALID: {exc}', file=sys.stderr)
        return 1
    files = list(STATIC_FILES)
    publisher_ref = manifest.get('contracts', {}).get('publisher_profile')
    if not safe_ref(publisher_ref):
        errors.append('invalid publisher profile reference')
    else:
        files.append((publisher_ref, 'publisher-profile.schema.json'))
    for rel, schema_name in files:
        try:
            jsonschema.validate(load(pack / rel), load(schemas / schema_name))
        except Exception as exc:
            errors.append(f'{rel}: {exc}')
    if errors:
        print('\n'.join('INVALID: ' + item for item in errors), file=sys.stderr)
        return 1
    print(f'VALID COMPLETE MARKETPLACE SCHEMAS: {pack}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
