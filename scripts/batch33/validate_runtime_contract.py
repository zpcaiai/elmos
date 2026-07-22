#!/usr/bin/env python3
from __future__ import annotations
import argparse, sys
from pathlib import Path
from _graph_validation import validate_graph

def main() -> int:
    p = argparse.ArgumentParser(); p.add_argument('contract'); args = p.parse_args()
    path = Path(args.contract)
    schema = Path(__file__).resolve().parents[2] / 'schemas' / 'batch33' / 'runtime-architecture-contract.schema.json'
    errors = validate_graph(path, schema, ('components','connections','identities','data_flows','policies'), ('references',))
    if errors:
        print('\n'.join('ERROR: ' + e for e in errors), file=sys.stderr); return 1
    print('OK: runtime architecture contract')
    return 0
if __name__ == '__main__': raise SystemExit(main())
