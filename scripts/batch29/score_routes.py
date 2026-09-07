#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output',required=True); a=p.parse_args()
    data=json.loads(Path(a.input).read_text()); weights=data['weights']; out=[]
    if abs(sum(weights.values())-1.0)>1e-6: raise SystemExit('weights must sum to 1')
    for c in data['candidates']:
        score=0.0
        for k,w in weights.items():
            v=float(c.get(k,0))
            if not 0<=v<=5: raise SystemExit(f'{c.get("route_key")} {k} must be 0..5')
            score += v*w
        decision='approve' if score>=4 else 'discovery' if score>=3 else 'defer' if score>=2 else 'reject'
        out.append({'route_key':c['route_key'],'score':round(score,3),'decision':decision,'evidence_notes':c.get('evidence_notes',[])})
    out.sort(key=lambda x:x['score'],reverse=True)
    Path(a.output).write_text(json.dumps({'results':out},indent=2)+'\n')
    print(Path(a.output))
    return 0
if __name__=='__main__': raise SystemExit(main())
