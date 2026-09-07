#!/usr/bin/env python3
from __future__ import annotations
import argparse
from _common import load,write

def main():
 p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output',required=True); a=p.parse_args(); data=load(a.input); out=[]
 for c in data.get('candidates',[]):
  score=3*c.get('business_value',0)+3*c.get('risk_reduction',0)+2*c.get('evidence_readiness',0)+2*c.get('tooling_readiness',0)+2*c.get('representativeness',0)-2*c.get('cost',0)-3*c.get('unknowns',0)
  out.append({'key':c.get('key'),'score':score,'decision':'approve' if score>=60 else 'research' if score>=30 else 'defer'})
 out.sort(key=lambda x:x['score'],reverse=True); write(a.output,{'schema_version':1,'results':out}); return 0
if __name__=='__main__': raise SystemExit(main())
