#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')
MODES = ('migration', 'upgrade', 'modernization', 'coexistence')


def load(path: Path):
    return json.loads(path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description='Scaffold a version-specific Batch 30 framework pack.')
    parser.add_argument('--source-framework', required=True)
    parser.add_argument('--target-framework', required=True)
    parser.add_argument('--source-runtime', required=True)
    parser.add_argument('--target-runtime', required=True)
    parser.add_argument('--mode', choices=MODES, default='migration')
    parser.add_argument('--pack-key')
    parser.add_argument('--repo-root', default='.')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    for value in [args.source_framework, args.target_framework, args.source_runtime, args.target_runtime]:
        if not SLUG.fullmatch(value):
            parser.error(f'invalid slug: {value!r}')
    pack_key = args.pack_key or f'{args.source_framework}-to-{args.target_framework}'
    if not SLUG.fullmatch(pack_key):
        parser.error(f'invalid pack key: {pack_key!r}')
    root = Path(args.repo_root).resolve()
    pack = root / 'framework-packs' / pack_key
    if pack.exists() and not args.force:
        print(f'EXISTS: {pack}')
        return 0
    dirs = [
        'source-fingerprint',
        'contracts/web','contracts/di','contracts/configuration','contracts/validation',
        'contracts/security','contracts/persistence','contracts/transaction',
        'contracts/messaging','contracts/cache','contracts/scheduler','contracts/lifecycle',
        'target-profile/dependency-locks','target-profile/scaffold','target-profile/contract-tests',
        'recipes','adapters','compatibility','coexistence',
        'corpus/development/smoke','corpus/development/contracts','corpus/development/negative',
        'corpus/holdout','corpus/real-repository','certification'
    ]
    for rel in dirs:
        (pack / rel).mkdir(parents=True, exist_ok=True)
    template_root = root / 'templates' / 'batch30'
    if not template_root.exists():
        template_root = Path(__file__).resolve().parents[2] / 'templates' / 'batch30'
    manifest = load(template_root / 'framework-pack.json')
    manifest['pack_key'] = pack_key
    manifest['mode'] = args.mode
    manifest['source']['framework'] = args.source_framework
    manifest['source']['runtime'] = args.source_runtime
    manifest['source']['framework_versions'] = []
    manifest['source']['runtime_versions'] = []
    manifest['target']['framework'] = args.target_framework
    manifest['target']['runtime'] = args.target_runtime
    manifest['target']['framework_versions'] = []
    manifest['target']['runtime_versions'] = []
    support = load(template_root / 'support-matrix.json')
    support['pack_key'] = pack_key
    profile = load(template_root / 'target-profile.json')
    profile['profile_key'] = f'{pack_key}-target'
    profile['framework'] = args.target_framework
    profile['runtime'] = args.target_runtime
    evidence = load(template_root / 'evidence.json')
    evidence['pack_key'] = pack_key
    certification = load(template_root / 'certification.json')
    certification['pack_key'] = pack_key
    files = {
        pack/'pack.json': manifest,
        pack/'support-matrix.json': support,
        pack/'version-matrix.json': {'schema_version':1,'pack_key':pack_key,'tuples':[],'upgrade_edges':[]},
        pack/'source-fingerprint'/'manifest.json': {'schema_version':1,'pack_key':pack_key,'capabilities':[],'profiles':[],'generated_assets':[],'unknowns':[]},
        pack/'source-fingerprint'/'evidence.json': {'schema_version':1,'pack_key':pack_key,'runs':[],'coverage':0},
        pack/'target-profile'/'profile.json': profile,
        pack/'compatibility'/'manifest.json': {'schema_version':1,'pack_key':pack_key,'components':[],'budget':{'max_components':5,'max_wrapped_contract_ratio':0.10,'prohibited_domains':['authentication','authorization','transaction-core','money-calculation']}},
        pack/'coexistence'/'manifest.json': {'schema_version':1,'pack_key':pack_key,'enabled':False,'components':[],'exit_criteria':[]},
        pack/'certification'/'evidence.json': evidence,
        pack/'certification'/'certification.json': certification,
    }
    for path, data in files.items():
        if path.exists() and not args.force:
            continue
        path.write_text(json.dumps(data, indent=2) + '\n')
    (pack/'README.md').write_text(f'# {pack_key}\n\nDirectional, version-specific Batch 30 framework pack.\n')
    print(pack)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
