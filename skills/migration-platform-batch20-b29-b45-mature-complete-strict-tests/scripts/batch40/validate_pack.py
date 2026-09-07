#!/usr/bin/env python3
from pathlib import Path
import sys,json
from _common import load,valid_digest
CFG=load(Path(__file__).with_name('config.json'))
def main():
 p=Path(sys.argv[1]); f=[]
 for rel in ['pack.json','support-matrix.json','profile.json','certification/evidence.json','certification/certification.json']:
  if not (p/rel).is_file(): f.append('missing '+rel)
 if f: print('\n'.join(f),file=sys.stderr); return 2
 pack=load(p/'pack.json'); sm=load(p/'support-matrix.json')
 for k in ['pack_key','status','artifact_digest','environment_digest','owner']:
  if not pack.get(k): f.append('pack missing '+k)
 if pack.get('status') not in COMMON: f.append('invalid status')
 if not isinstance(sm.get('capabilities'),list) or len(sm['capabilities'])<CFG['SKILL_COUNT']: f.append('support matrix incomplete')
 known={x.get('capability_id') for x in sm.get('capabilities',[])}
 missing=set(CFG['SKILL_NAMES'])-known
 if missing: f.append('missing capabilities: '+','.join(sorted(missing)))
 for b in CFG['REQUIRED_BATCHES']:
  if b not in pack.get('required_batches',[]): f.append(f'required batch {b} missing')
 if f: print('\n'.join(f),file=sys.stderr); return 2
 print('PACK VALID'); return 0
COMMON=['research', 'experimental', 'limited', 'certified', 'deprecated', 'blocked']
if __name__=='__main__': raise SystemExit(main())
