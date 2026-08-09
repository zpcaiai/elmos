#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
from _common import load

def main():
 p=Path(sys.argv[1]); r=load(p); errors=[]; ids=set()
 for o in r.get('oracles',[]):
  oid=o.get('oracle_id')
  if not oid or oid in ids: errors.append(f'duplicate or missing oracle_id: {oid}')
  ids.add(oid)
  if o.get('type')=='llm-advisory' and o.get('trust_level') in {'authoritative','strong'}: errors.append(f'LLM oracle {oid} cannot be authoritative/strong')
  if o.get('independence')=='dependent' and o.get('trust_level')=='authoritative': errors.append(f'dependent oracle {oid} cannot be authoritative')
 for rule in r.get('precedence_rules',[]):
  for oid in rule.get('ordered_oracles',[]):
   if oid not in ids: errors.append(f'precedence references unknown oracle {oid}')
 for c in r.get('conflicts',[]):
  for oid in c.get('oracle_ids',[]):
   if oid not in ids: errors.append(f'conflict references unknown oracle {oid}')
 if errors: print('\n'.join('ERROR: '+x for x in errors),file=sys.stderr); return 1
 print(f'OK: {len(ids)} oracles'); return 0
if __name__=='__main__': raise SystemExit(main())
