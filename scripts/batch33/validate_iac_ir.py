#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import jsonschema

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument('ir'); args = p.parse_args()
    path = Path(args.ir); data = json.loads(path.read_text())
    schema = json.loads((Path(__file__).resolve().parents[2] / 'schemas' / 'batch33' / 'iac-ir.schema.json').read_text())
    errors: list[str] = []
    try: jsonschema.validate(data, schema)
    except Exception as exc: errors.append(str(exc))
    ids: set[str] = set()
    for resource in data.get('resources', []):
        rid = resource.get('id')
        if rid in ids: errors.append(f'duplicate id: {rid}')
        ids.add(rid)
    for resource in data.get('resources', []):
        for ref in resource.get('depends_on', []):
            if ref not in ids: errors.append(f'{resource.get("id")}: unknown dependency {ref}')
    mapped = {x.get('node_id') for x in data.get('source_map', []) if isinstance(x, dict)}
    for rid in ids:
        if rid not in mapped: errors.append(f'{rid}: missing source map')
    if errors:
        print('\n'.join('ERROR: ' + e for e in errors), file=sys.stderr); return 1
    print('OK: IaC IR')
    return 0
if __name__ == '__main__': raise SystemExit(main())
