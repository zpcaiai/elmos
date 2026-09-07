#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re
from pathlib import Path

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,95}$')
MODES = ('assessment', 'migration', 'upgrade', 'modernization', 'coexistence')

def load(path: Path):
    return json.loads(path.read_text())

def exact(value: str, label: str, parser: argparse.ArgumentParser) -> str:
    if value.strip().lower() in {'', 'latest', '*', 'x', 'unset'}:
        parser.error(f'exact {label} required')
    return value

def main() -> int:
    parser = argparse.ArgumentParser(description='Scaffold an exact directional Batch 32 client modernization pack.')
    parser.add_argument('--source-stack', required=True)
    parser.add_argument('--target-stack', required=True)
    parser.add_argument('--source-version', required=True)
    parser.add_argument('--target-version', required=True)
    parser.add_argument('--source-language', required=True)
    parser.add_argument('--target-language', required=True)
    parser.add_argument('--source-language-version', required=True)
    parser.add_argument('--target-language-version', required=True)
    parser.add_argument('--source-runtime', required=True)
    parser.add_argument('--target-runtime', required=True)
    parser.add_argument('--source-runtime-version', required=True)
    parser.add_argument('--target-runtime-version', required=True)
    parser.add_argument('--source-build-tool', required=True)
    parser.add_argument('--target-build-tool', required=True)
    parser.add_argument('--source-package-manager', required=True)
    parser.add_argument('--target-package-manager', required=True)
    parser.add_argument('--mode', choices=MODES, default='modernization')
    parser.add_argument('--pack-key')
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    for value in (args.source_stack, args.target_stack):
        if not SLUG.fullmatch(value):
            parser.error(f'invalid stack slug: {value!r}')
    key = args.pack_key or f'{args.source_stack}-to-{args.target_stack}'
    if not SLUG.fullmatch(key):
        parser.error(f'invalid pack key: {key!r}')
    for label in (
        'source_version', 'target_version',
        'source_language_version', 'target_language_version',
        'source_runtime_version', 'target_runtime_version',
    ):
        exact(getattr(args, label), label.replace('_', ' '), parser)

    root = Path(args.repo_root).resolve()
    pack = root / 'client-packs' / key
    if pack.exists() and not args.force:
        print(f'EXISTS: {pack}')
        return 0

    directories = [
        'source-fingerprint/static', 'source-fingerprint/runtime',
        'source-snapshots/assets', 'source-snapshots/runtime',
        'ui-ir/routes', 'ui-ir/components', 'ui-ir/state', 'ui-ir/forms',
        'ui-ir/resources', 'ui-ir/accessibility',
        'target-profile/config', 'target-profile/dependency-locks',
        'transformations/routes', 'transformations/components',
        'transformations/state', 'transformations/forms',
        'transformations/security', 'transformations/rendering',
        'design-system/tokens', 'design-system/components',
        'acceptance/browser', 'acceptance/device', 'acceptance/locales',
        'corpus/development/journeys', 'corpus/development/negative',
        'corpus/holdout', 'corpus/representative-workloads',
        'visual-baselines/approved', 'accessibility/reports',
        'certification',
    ]
    for directory in directories:
        (pack / directory).mkdir(parents=True, exist_ok=True)

    templates = root / 'templates' / 'batch32'
    if not templates.exists():
        templates = Path(__file__).resolve().parents[2] / 'templates' / 'batch32'

    manifest = load(templates / 'client-pack.json')
    manifest['pack_key'] = key
    manifest['mode'] = args.mode
    source = {
        'stack': args.source_stack,
        'versions': [args.source_version],
        'language': args.source_language,
        'language_versions': [args.source_language_version],
        'runtime': args.source_runtime,
        'runtime_versions': [args.source_runtime_version],
        'build_tool': args.source_build_tool,
        'package_manager': args.source_package_manager,
        'router': [], 'renderer': [], 'state': [], 'forms': [],
        'styling': [], 'design_system': [], 'api_client': [],
        'identity': [], 'i18n': [], 'test_tools': [],
        'browsers': ['chromium-UNSET'], 'devices': [],
    }
    target = {
        'stack': args.target_stack,
        'versions': [args.target_version],
        'language': args.target_language,
        'language_versions': [args.target_language_version],
        'runtime': args.target_runtime,
        'runtime_versions': [args.target_runtime_version],
        'build_tool': args.target_build_tool,
        'package_manager': args.target_package_manager,
        'router': [], 'renderer': [], 'state': [], 'forms': [],
        'styling': [], 'design_system': [], 'api_client': [],
        'identity': [], 'i18n': [], 'test_tools': [],
        'browsers': ['chromium-UNSET'], 'devices': [],
    }
    manifest['source'] = source
    manifest['target'] = target

    support = load(templates / 'support-matrix.json')
    support['pack_key'] = key

    fingerprint = load(templates / 'source-fingerprint.json')
    fingerprint['pack_key'] = key
    fingerprint['source_tuple'] = source

    ui_ir = load(templates / 'ui-interaction-ir.json')
    ui_ir['pack_key'] = key

    target_profile = load(templates / 'target-profile.json')
    target_profile.update({
        'profile_key': f'{key}-target',
        'framework': args.target_stack,
        'versions': [args.target_version],
        'language': args.target_language,
        'language_versions': [args.target_language_version],
        'runtime': args.target_runtime,
        'runtime_versions': [args.target_runtime_version],
        'build_tool': args.target_build_tool,
        'package_manager': args.target_package_manager,
    })

    acceptance = load(templates / 'acceptance-profile.json')
    acceptance['profile_key'] = f'{key}-acceptance'

    evidence = load(templates / 'evidence.json')
    evidence['pack_key'] = key

    certification = load(templates / 'certification.json')
    certification['pack_key'] = key
    certification['exact_tuple'] = {'source': source, 'target': target}

    route_matrix = {
        'schema_version': 1,
        'pack_key': key,
        'tuples': [{
            'source_stack': args.source_stack,
            'source_version': args.source_version,
            'target_stack': args.target_stack,
            'target_version': args.target_version,
            'status': 'research',
            'evidence_refs': [],
        }],
        'recertification_triggers': [],
    }

    files = {
        pack / 'pack.json': manifest,
        pack / 'support-matrix.json': support,
        pack / 'route-matrix.json': route_matrix,
        pack / 'source-fingerprint' / 'fingerprint.json': fingerprint,
        pack / 'source-fingerprint' / 'evidence.json': {
            'schema_version': 1, 'pack_key': key, 'runs': [],
            'coverage': 0, 'evidence_refs': [],
        },
        pack / 'ui-ir' / 'model.json': ui_ir,
        pack / 'target-profile' / 'profile.json': target_profile,
        pack / 'acceptance' / 'acceptance-profile.json': acceptance,
        pack / 'certification' / 'evidence.json': evidence,
        pack / 'certification' / 'certification.json': certification,
    }
    for path, data in files.items():
        if not path.exists() or args.force:
            path.write_text(json.dumps(data, indent=2) + '\n')

    (pack / 'certification' / 'gap-inventory.md').write_text(
        '# Gap inventory\n\n'
        '- Assign product, maintenance, UX, and accessibility owners.\n'
        '- Capture exact routers, renderers, state, forms, identity, browsers, and devices.\n'
        '- Add real build, launch, browser/device, visual, accessibility, holdout, and representative workload evidence.\n'
    )
    (pack / 'README.md').write_text(
        f'# {key}\n\nDirectional, exact Batch 32 client modernization pack.\n'
    )
    print(pack)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
