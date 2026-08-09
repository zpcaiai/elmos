#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output',required=True); a=p.parse_args()
    data=json.loads(Path(a.input).read_text()); weights=data.get('weights',{}); results=[]
    for c in data.get('candidates',[]):
        score=sum(float(c.get(k,0))*float(w) for k,w in weights.items())
        if score>=12: decision='approve'
        elif score>=6: decision='sequence'
        else: decision='research'
        results.append({'pack_key':c.get('pack_key'),'score':round(score,3),'decision':decision,'evidence_notes':c.get('evidence_notes',[])})
    results.sort(key=lambda x:x['score'],reverse=True)
    Path(a.output).write_text(json.dumps({'schema_version':1,'results':results},indent=2)+'\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
