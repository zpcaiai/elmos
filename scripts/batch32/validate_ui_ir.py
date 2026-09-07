#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

GROUPS = [
    'routes', 'views', 'components', 'states', 'actions', 'effects',
    'forms', 'bindings', 'permissions', 'resources', 'design_tokens',
    'accessibility',
]

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('ir_file')
    args = parser.parse_args()
    path = Path(args.ir_file)
    errors: list[str] = []
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        print(f'ERROR: {path}: {exc}', file=sys.stderr)
        return 1

    for key in ('schema_version', 'pack_key', 'source_snapshot_digest', *GROUPS, 'source_map', 'unknowns'):
        if key not in data:
            errors.append(f'missing key: {key}')
    if data.get('schema_version') != 1:
        errors.append('schema_version must be 1')
    if str(data.get('source_snapshot_digest', '')).upper() in {'', 'UNSET'}:
        errors.append('source_snapshot_digest is unset')

    identifiers: set[str] = set()
    nodes: list[dict] = []
    for group in GROUPS:
        values = data.get(group, [])
        if not isinstance(values, list):
            errors.append(f'{group} must be an array')
            continue
        for node in values:
            if not isinstance(node, dict):
                errors.append(f'{group} node must be object')
                continue
            for key in ('id', 'kind', 'name', 'source_refs'):
                if key not in node:
                    errors.append(f'{group} node missing {key}')
            identifier = node.get('id')
            if identifier in identifiers:
                errors.append(f'duplicate node id: {identifier}')
            if identifier:
                identifiers.add(identifier)
            if not node.get('source_refs'):
                errors.append(f'{identifier or group}: source_refs empty')
            nodes.append(node)

    for node in nodes:
        for reference in node.get('references', []):
            if reference not in identifiers:
                errors.append(f"{node.get('id')}: unknown reference {reference}")

    mapped = {entry.get('node_id') for entry in data.get('source_map', []) if isinstance(entry, dict)}
    missing_map = sorted(identifier for identifier in identifiers if identifier not in mapped)
    if missing_map:
        errors.append(f'source_map missing nodes: {", ".join(missing_map[:10])}')

    if errors:
        print('\n'.join('ERROR: ' + error for error in errors), file=sys.stderr)
        return 1
    print(f'OK: {path} nodes={len(identifiers)}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
