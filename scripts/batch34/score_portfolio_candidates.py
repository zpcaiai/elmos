#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser(); p.add_argument('candidates'); p.add_argument('--output',required=True); a=p.parse_args(); data=json.loads(Path(a.candidates).read_text()); weights=data.get('weights',{}); results=[]
 for c in data.get('candidates',[]):
  score=sum(float(c.get(k,0))*float(w) for k,w in weights.items()); decision='approve' if score>=20 else 'research' if score>=10 else 'defer'; results.append({'pack_key':c['pack_key'],'score':round(score,3),'decision':decision,'evidence_notes':c.get('evidence_notes',[])})
 results.sort(key=lambda x:x['score'],reverse=True); out={'schema_version':1,'results':results}; Path(a.output).write_text(json.dumps(out,indent=2)+'\n'); print(Path(a.output)); return 0
if __name__=='__main__': raise SystemExit(main())
