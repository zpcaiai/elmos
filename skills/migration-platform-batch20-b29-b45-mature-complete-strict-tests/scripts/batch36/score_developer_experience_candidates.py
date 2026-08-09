#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path

def main():
 p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output',required=True); a=p.parse_args(); d=json.loads(Path(a.input).read_text()); results=[]
 for c in d.get('candidates',[]):
  score=2*c.get('business_value',0)+2*c.get('developer_reach',0)+2*c.get('security_readiness',0)+c.get('existing_assets',0)-2*c.get('implementation_effort',0)
  decision='approve' if score>=35 else 'research' if score>=20 else 'defer'; results.append({'pack_key':c['pack_key'],'score':score,'decision':decision})
 results.sort(key=lambda x:(-x['score'],x['pack_key'])); out={'schema_version':1,'results':results}; Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); return 0
if __name__=='__main__': raise SystemExit(main())
