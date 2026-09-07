#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import PurePosixPath
from _common import load

def bad_path(s):
 p=PurePosixPath(s); return p.is_absolute() or '..' in p.parts

def main():
 m=load(sys.argv[1]); errors=[]; ids=set()
 for n in m.get('nodes',[]):
  if n.get('node_id') in ids: errors.append(f'duplicate node {n.get("node_id")}')
  ids.add(n.get('node_id'))
  if bad_path(n.get('path','')): errors.append(f'unsafe path {n.get("path")}')
 for e in m.get('edges',[]):
  if e.get('from') not in ids: errors.append(f'unknown from {e.get("from")}')
  if e.get('to') not in ids: errors.append(f'unknown to {e.get("to")}')
  if e.get('relation')=='exact' and float(e.get('confidence',0))<0.99: errors.append('exact relation requires confidence >= 0.99')
 if errors: print('\n'.join('ERROR: '+e for e in errors),file=sys.stderr); return 1
 print('OK: navigation map'); return 0
if __name__=='__main__': raise SystemExit(main())
