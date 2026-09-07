#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from _common import load,write

def main():
 p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output',required=True); a=p.parse_args(); d=load(a.input); out=[]
 for c in d.get('candidates',[]):
  score=2*c.get('strategic_value',0)+2*c.get('customer_demand',0)+c.get('reuse',0)-2*c.get('security_risk',0)-c.get('implementation_effort',0)
  decision='approve' if c.get('decision')=='approve' and score>=8 else 'reject'
  out.append({'key':c.get('key'),'score':score,'decision':decision})
 out.sort(key=lambda x:x['score'],reverse=True); write(a.output,{'schema_version':1,'results':out}); return 0
if __name__=='__main__': raise SystemExit(main())
