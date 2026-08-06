#!/usr/bin/env python3
import argparse,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(); p.add_argument('--out',default='compiled-contracts'); a=p.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
index=[]
for f in sorted((ROOT/'contracts').glob('batch-*/*.json')):
 o=json.loads(f.read_text()); canonical=json.dumps(o,sort_keys=True,separators=(',',':')).encode(); digest=hashlib.sha256(canonical).hexdigest();
 compiled={'contract':o,'canonicalSha256':'sha256:'+digest,'compiledVersion':1}; target=out/(o['id']+'.compiled.json'); target.write_text(json.dumps(compiled,indent=2)+'\n'); index.append({'id':o['id'],'path':str(target),'sha256':'sha256:'+digest})
(out/'index.json').write_text(json.dumps(index,indent=2)+'\n'); print(f'compiled {len(index)} contracts to {out}')
