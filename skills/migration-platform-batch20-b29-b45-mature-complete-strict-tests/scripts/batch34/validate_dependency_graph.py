#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import jsonschema
from _graph_validation import unique_ids
def main():
 p=argparse.ArgumentParser(); p.add_argument('graph'); a=p.parse_args(); path=Path(a.graph); data=json.loads(path.read_text()); schema=json.loads((Path(__file__).resolve().parents[2]/'schemas/batch34/dependency-graph.schema.json').read_text()); errors=[]
 try: jsonschema.validate(data,schema)
 except Exception as e: errors.append(str(e))
 nodes,e=unique_ids(data.get('nodes',[]),'nodes'); errors+=e; edges,e=unique_ids(data.get('edges',[]),'edges'); errors+=e
 for edge in data.get('edges',[]):
  if edge.get('from') not in nodes: errors.append(f"edge {edge.get('id')}: unknown from {edge.get('from')}")
  if edge.get('to') not in nodes: errors.append(f"edge {edge.get('id')}: unknown to {edge.get('to')}")
  if edge.get('from')==edge.get('to'): errors.append(f"edge {edge.get('id')}: self edge")
 if errors: print('\n'.join('ERROR: '+x for x in errors),file=sys.stderr); return 1
 print(f'OK: graph nodes={len(nodes)} edges={len(edges)}'); return 0
if __name__=='__main__': raise SystemExit(main())
