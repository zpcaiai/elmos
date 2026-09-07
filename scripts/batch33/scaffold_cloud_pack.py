#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, re, shutil
from pathlib import Path

SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,95}$')

def load(path: Path):
    return json.loads(path.read_text())

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument('--source-platform', required=True)
    p.add_argument('--target-platform', required=True)
    p.add_argument('--source-provider', required=True)
    p.add_argument('--target-provider', required=True)
    p.add_argument('--source-region', required=True)
    p.add_argument('--target-region', required=True)
    p.add_argument('--source-iac-tool', required=True)
    p.add_argument('--source-iac-version', required=True)
    p.add_argument('--target-iac-tool', required=True)
    p.add_argument('--target-iac-version', required=True)
    p.add_argument('--source-runtime', required=True)
    p.add_argument('--source-runtime-version', required=True)
    p.add_argument('--target-runtime', required=True)
    p.add_argument('--target-runtime-version', required=True)
    p.add_argument('--source-account-model', default='single-account')
    p.add_argument('--target-account-model', default='single-account')
    p.add_argument('--source-ci', default='UNSET')
    p.add_argument('--source-ci-version', default='UNSET')
    p.add_argument('--target-ci', default='UNSET')
    p.add_argument('--target-ci-version', default='UNSET')
    p.add_argument('--mode', default='migration')
    p.add_argument('--pack-key')
    p.add_argument('--repo-root', default='.')
    p.add_argument('--force', action='store_true')
    args = p.parse_args()

    key = args.pack_key or f'{args.source_iac_tool}-{args.source_provider}-to-{args.target_iac_tool}-{args.target_provider}'
    key = key.lower().replace('_', '-').replace('.', '-')
    if not SLUG.fullmatch(key):
        raise SystemExit(f'invalid pack key: {key}')

    repo = Path(args.repo_root).resolve()
    templates = Path(__file__).resolve().parents[2] / 'templates' / 'batch33'
    pack = repo / 'cloud-packs' / key
    if pack.exists() and any(pack.iterdir()) and not args.force:
        raise SystemExit(f'pack exists: {pack}; use --force to overwrite template files')

    dirs = [
        'source-fingerprint', 'runtime-architecture', 'iac-ir', 'target-profile', 'validation',
        'transformations', 'mappings', 'adapters', 'container', 'orchestration', 'pipelines',
        'managed-services', 'gateway', 'observability', 'security', 'policies', 'state', 'rollout', 'cost', 'drift',
        'corpus/development', 'corpus/negative', 'corpus/holdout', 'corpus/representative-workloads',
        'certification',
    ]
    for rel in dirs:
        (pack / rel).mkdir(parents=True, exist_ok=True)

    source = {
        'platform': args.source_platform,
        'provider': args.source_provider,
        'regions': [args.source_region],
        'account_model': args.source_account_model,
        'iac_tool': {'name': args.source_iac_tool, 'version': args.source_iac_version},
        'runtime': {'name': args.source_runtime, 'version': args.source_runtime_version},
        'orchestrator': {'name': 'none', 'version': 'n/a'},
        'ci_cd': {'name': args.source_ci, 'version': args.source_ci_version},
        'state_backend': {'type': 'UNSET', 'locking': 'UNSET', 'encryption': 'UNSET'},
        'services': [],
    }
    target = {
        'platform': args.target_platform,
        'provider': args.target_provider,
        'regions': [args.target_region],
        'account_model': args.target_account_model,
        'iac_tool': {'name': args.target_iac_tool, 'version': args.target_iac_version},
        'runtime': {'name': args.target_runtime, 'version': args.target_runtime_version},
        'orchestrator': {'name': 'none', 'version': 'n/a'},
        'ci_cd': {'name': args.target_ci, 'version': args.target_ci_version},
        'state_backend': {'type': 'UNSET', 'locking': 'UNSET', 'encryption': 'UNSET'},
        'services': [],
    }

    manifest = load(templates / 'cloud-pack.json')
    manifest.update({'pack_key': key, 'mode': args.mode, 'source': source, 'target': target})
    support = load(templates / 'support-matrix.json'); support['pack_key'] = key
    fingerprint = load(templates / 'source-fingerprint.json'); fingerprint['pack_key'] = key; fingerprint['source_tuple'] = source
    runtime = load(templates / 'runtime-architecture-contract.json'); runtime['pack_key'] = key
    ir = load(templates / 'iac-ir.json'); ir['pack_key'] = key
    target_profile = load(templates / 'target-profile.json')
    target_profile.update({'profile_key': f'{key}-target', 'provider': args.target_provider, 'regions': [args.target_region], 'account_model': args.target_account_model, 'iac_tool': target['iac_tool']})
    validation = load(templates / 'validation-profile.json'); validation['profile_key'] = f'{key}-validation'
    evidence = load(templates / 'evidence.json'); evidence['pack_key'] = key
    cert = load(templates / 'certification.json'); cert['pack_key'] = key; cert['exact_tuple'] = {'source': source, 'target': target}
    route = load(templates / 'route-matrix.json'); route['pack_key'] = key; route['tuples'] = [{'source': source, 'target': target, 'status': 'research', 'evidence_refs': []}]

    files = {
        pack / 'pack.json': manifest,
        pack / 'support-matrix.json': support,
        pack / 'route-matrix.json': route,
        pack / 'source-fingerprint' / 'fingerprint.json': fingerprint,
        pack / 'runtime-architecture' / 'contract.json': runtime,
        pack / 'iac-ir' / 'model.json': ir,
        pack / 'target-profile' / 'profile.json': target_profile,
        pack / 'validation' / 'validation-profile.json': validation,
        pack / 'certification' / 'evidence.json': evidence,
        pack / 'certification' / 'certification.json': cert,
    }
    for path, data in files.items():
        if not path.exists() or args.force:
            path.write_text(json.dumps(data, indent=2) + '\n')

    (pack / 'certification' / 'gap-inventory.md').write_text(
        '# Gap inventory\n\n'
        '- Assign accountable, maintenance, cloud, security, network, data, SRE, and cost owners.\n'
        '- Capture static definitions, live runtime inventory, state, identities, networks, services, pipelines, drift, and cost.\n'
        '- Add typed Runtime Architecture Contract and IaC IR nodes with source maps.\n'
        '- Add real plan, sandbox apply/runtime, rollback, destroy, holdout, and representative workload evidence.\n'
    )
    (pack / 'README.md').write_text(f'# {key}\n\nDirectional exact Batch 33 Cloud/IaC/DevOps modernization pack.\n')
    print(pack)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
