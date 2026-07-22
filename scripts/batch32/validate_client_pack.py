#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REQUIRED_DIRS = [
    'source-fingerprint', 'source-snapshots', 'ui-ir', 'target-profile',
    'transformations', 'design-system', 'acceptance', 'corpus/development',
    'corpus/holdout', 'corpus/representative-workloads',
    'visual-baselines', 'accessibility', 'certification',
]
PACK_STATUS = {'research', 'experimental', 'limited', 'certified', 'deprecated', 'blocked'}
CAP_STATUS = {'certified', 'supported', 'conditional', 'experimental', 'detected-only', 'blocked'}
MODES = {'assessment', 'migration', 'upgrade', 'modernization', 'coexistence'}
BAD = {'', 'UNSET', 'UNASSIGNED', 'latest', '*', 'x', None}

def load(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        raise ValueError(f'{path}: {exc}') from exc

def tuple_errors(label: str, value: dict) -> list[str]:
    errors: list[str] = []
    required = [
        'stack', 'versions', 'language', 'language_versions', 'runtime',
        'runtime_versions', 'build_tool', 'package_manager', 'router',
        'renderer', 'state', 'forms', 'styling', 'design_system',
        'api_client', 'identity', 'i18n', 'test_tools', 'browsers', 'devices',
    ]
    for key in required:
        if key not in value:
            errors.append(f'{label} missing key: {key}')
    for key in ('stack', 'language', 'runtime', 'build_tool', 'package_manager'):
        if value.get(key) in BAD:
            errors.append(f'{label} has unset {key}')
    for field in ('versions', 'language_versions', 'runtime_versions'):
        values = value.get(field, [])
        if not values:
            errors.append(f'{label} {field} empty')
        for item in values:
            if str(item).strip().lower() in {'', 'latest', '*', 'x', 'unset'}:
                errors.append(f'{label} uses floating/unset {field}: {item}')
    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('pack_dir')
    args = parser.parse_args()
    pack = Path(args.pack_dir)
    errors: list[str] = []

    if not pack.is_dir():
        errors.append(f'missing pack dir: {pack}')
    for relative in REQUIRED_DIRS:
        if not (pack / relative).exists():
            errors.append(f'missing: {pack / relative}')

    manifest: dict = {}
    try:
        manifest = load(pack / 'pack.json')
        for key in (
            'schema_version', 'pack_key', 'version', 'mode', 'status',
            'owner', 'maintenance_owner', 'ux_owner', 'accessibility_owner',
            'source', 'target', 'scope', 'paths', 'gates',
        ):
            if key not in manifest:
                errors.append(f'pack.json missing key: {key}')
        if manifest.get('status') not in PACK_STATUS:
            errors.append('invalid pack status')
        if manifest.get('mode') not in MODES:
            errors.append('invalid pack mode')
        for key in ('owner', 'maintenance_owner', 'ux_owner', 'accessibility_owner'):
            if manifest.get(key) in BAD:
                errors.append(f'{key} is unassigned')
        errors += tuple_errors('source', manifest.get('source', {}))
        errors += tuple_errors('target', manifest.get('target', {}))
        scope = manifest.get('scope', {})
        for key in ('journeys', 'routes', 'component_roots', 'excluded'):
            if key not in scope:
                errors.append(f'scope missing {key}')
    except Exception as exc:
        errors.append(str(exc))

    try:
        support = load(pack / 'support-matrix.json')
        if support.get('pack_key') != manifest.get('pack_key'):
            errors.append('support matrix pack_key mismatch')
        identifiers: set[str] = set()
        for capability in support.get('capabilities', []):
            identifier = capability.get('id')
            if identifier in identifiers:
                errors.append(f'duplicate capability id: {identifier}')
            identifiers.add(identifier)
            status = capability.get('status')
            if status not in CAP_STATUS:
                errors.append(f'invalid capability status: {identifier}')
            if capability.get('owner') in BAD:
                errors.append(f'capability owner unassigned: {identifier}')
            if status in {'certified', 'supported'} and not capability.get('evidence_refs'):
                errors.append(f'{status} capability lacks evidence: {identifier}')
            if status in {'conditional', 'blocked'} and not capability.get('reason'):
                errors.append(f'{status} capability lacks reason: {identifier}')
    except Exception as exc:
        errors.append(str(exc))

    try:
        profile = load(pack / 'target-profile' / 'profile.json')
        for key in (
            'profile_key', 'version', 'owner', 'framework', 'versions',
            'language', 'language_versions', 'runtime', 'runtime_versions',
            'build_tool', 'package_manager', 'rendering_strategy',
            'state_strategy', 'form_strategy', 'styling_strategy',
            'design_system_strategy', 'api_client_strategy', 'auth_strategy',
            'i18n_strategy', 'accessibility_profile', 'browser_matrix',
            'test_profiles', 'provision', 'health_check', 'security', 'lifecycle',
        ):
            if not profile.get(key):
                errors.append(f'target profile missing/non-empty key: {key}')
        if profile.get('owner') in BAD:
            errors.append('target profile owner unassigned')
        errors += tuple_errors('target profile', {
            'stack': profile.get('framework'),
            'versions': profile.get('versions'),
            'language': profile.get('language'),
            'language_versions': profile.get('language_versions'),
            'runtime': profile.get('runtime'),
            'runtime_versions': profile.get('runtime_versions'),
            'build_tool': profile.get('build_tool'),
            'package_manager': profile.get('package_manager'),
            'router': profile.get('router', []),
            'renderer': [profile.get('rendering_strategy')],
            'state': [profile.get('state_strategy')],
            'forms': [profile.get('form_strategy')],
            'styling': [profile.get('styling_strategy')],
            'design_system': [profile.get('design_system_strategy')],
            'api_client': [profile.get('api_client_strategy')],
            'identity': [profile.get('auth_strategy')],
            'i18n': [profile.get('i18n_strategy')],
            'test_tools': profile.get('test_profiles', []),
            'browsers': profile.get('browser_matrix', []),
            'devices': profile.get('device_profiles', []),
        })
    except Exception as exc:
        errors.append(str(exc))

    try:
        acceptance = load(pack / 'acceptance' / 'acceptance-profile.json')
        for key in (
            'profile_key', 'version', 'owner', 'browser_matrix', 'locales',
            'themes', 'rendering', 'visual', 'accessibility', 'interaction',
            'performance', 'seo', 'i18n', 'security', 'p0_journeys',
            'thresholds', 'exclusions',
        ):
            if key not in acceptance:
                errors.append(f'acceptance profile missing {key}')
        if acceptance.get('owner') in BAD:
            errors.append('acceptance profile owner unassigned')
    except Exception as exc:
        errors.append(str(exc))

    for path in (
        pack / 'route-matrix.json',
        pack / 'source-fingerprint' / 'fingerprint.json',
        pack / 'source-fingerprint' / 'evidence.json',
        pack / 'ui-ir' / 'model.json',
        pack / 'certification' / 'evidence.json',
        pack / 'certification' / 'certification.json',
    ):
        try:
            load(path)
        except Exception as exc:
            errors.append(str(exc))

    if errors:
        print('\n'.join('ERROR: ' + error for error in errors), file=sys.stderr)
        return 1
    print(f'OK: {pack}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
