#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load

def main():
 m=load(Path(sys.argv[1])); errors=[]; states=set(m.get('states',[]))
 if m.get('initial_state') not in states: errors.append('initial_state is not declared')
 seen=set()
 for c in m.get('commands',[]):
  key=(c.get('command'),tuple(c.get('from',[])),c.get('to'))
  if key in seen: errors.append(f'duplicate transition {key}')
  seen.add(key)
  for s in c.get('from',[]):
   if s not in states: errors.append(f'unknown from state {s}')
  if c.get('to') not in states: errors.append(f'unknown to state {c.get("to")}')
 for f in m.get('forbidden_transitions',[]):
  if f.get('from') not in states: errors.append(f'forbidden transition unknown state {f.get("from")}')
 if errors: print('\n'.join('ERROR: '+x for x in errors),file=sys.stderr); return 1
 print(f'OK: model states={len(states)} transitions={len(seen)}'); return 0
if __name__=='__main__': raise SystemExit(main())
