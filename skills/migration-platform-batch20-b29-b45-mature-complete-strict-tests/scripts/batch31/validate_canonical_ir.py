#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('ir_file'); a=p.parse_args(); path=Path(a.ir_file)
    errors=[]
    try: data=json.loads(path.read_text())
    except Exception as exc: print(f'ERROR: {path}: {exc}',file=sys.stderr); return 1
    for k in ['schema_version','pack_key','source_snapshot_digest','objects','queries','pipelines','unsupported_extensions']:
        if k not in data: errors.append(f'missing key: {k}')
    if data.get('schema_version') != 1: errors.append('schema_version must be 1')
    ids=set()
    all_nodes=[]
    for group in ['objects','queries','pipelines']:
        nodes=data.get(group,[])
        if not isinstance(nodes,list): errors.append(f'{group} must be an array'); continue
        for node in nodes:
            if not isinstance(node,dict): errors.append(f'{group} node must be object'); continue
            for k in ['id','kind','logical_name','source_ref','semantics','dependencies']:
                if k not in node: errors.append(f'{group} node missing {k}')
            nid=node.get('id')
            if nid in ids: errors.append(f'duplicate node id: {nid}')
            if nid: ids.add(nid)
            all_nodes.append(node)
    for node in all_nodes:
        for dep in node.get('dependencies',[]):
            if dep not in ids: errors.append(f"{node.get('id')}: unknown dependency {dep}")
    if str(data.get('source_snapshot_digest','')).upper() in {'','UNSET'}: errors.append('source_snapshot_digest is unset')
    if errors:
        print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
    print(f'OK: {path} nodes={len(ids)}'); return 0
if __name__=='__main__': raise SystemExit(main())
