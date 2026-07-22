#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil
from pathlib import Path

LANGUAGES = {'java','csharp','python','typescript'}

def main() -> int:
    p = argparse.ArgumentParser(description='Scaffold a directed Batch 29 route package.')
    p.add_argument('--source', required=True, choices=sorted(LANGUAGES))
    p.add_argument('--target', required=True, choices=sorted(LANGUAGES))
    p.add_argument('--repo-root', default='.')
    p.add_argument('--force', action='store_true')
    a = p.parse_args()
    if a.source == a.target:
        p.error('source and target must differ')
    root = Path(a.repo_root).resolve()
    route_key = f'{a.source}-to-{a.target}'
    route = root / 'routes' / route_key
    if route.exists() and not a.force:
        print(f'EXISTS: {route}')
        return 0
    route.mkdir(parents=True, exist_ok=True)
    for rel in ['lowering','mappings','compat-runtime','corpus/development/smoke','corpus/development/semantic','corpus/development/negative','corpus/holdout','corpus/real-repository','certification']:
        (route / rel).mkdir(parents=True, exist_ok=True)
    template_root = root / 'templates' / 'batch29'
    if not template_root.exists():
        template_root = Path(__file__).resolve().parents[2] / 'templates' / 'batch29'
    route_data = json.loads((template_root / 'route.json').read_text())
    route_data['route_key'] = route_key
    route_data['source'] = {'language':a.source,'versions':[],'engine_path':f'engines/{a.source}-engine'}
    route_data['target'] = {'language':a.target,'versions':[],'engine_path':f'engines/{a.target}-engine'}
    support = json.loads((template_root / 'support-matrix.json').read_text())
    support['route_key'] = route_key
    evidence = json.loads((template_root / 'evidence.json').read_text())
    evidence['route_key'] = route_key
    certification = json.loads((template_root / 'certification.json').read_text())
    certification['route_key'] = route_key
    files = {
        route/'route.json':route_data,
        route/'support-matrix.json':support,
        route/'compat-runtime'/'manifest.json':{'schema_version':1,'route_key':route_key,'components':[],'budget':{'max_components':5,'max_wrapped_callable_ratio':0.10,'prohibited_domains':['authentication','authorization','transaction-core','money-calculation']}},
        route/'certification'/'evidence.json':evidence,
        route/'certification'/'certification.json':certification,
    }
    for path, data in files.items():
        if path.exists() and not a.force:
            continue
        path.write_text(json.dumps(data, indent=2) + '\n')
    (route/'README.md').write_text(f'# {route_key}\n\nDirected Batch 29 migration route. Reverse direction is a separate route.\n')
    print(route)
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
