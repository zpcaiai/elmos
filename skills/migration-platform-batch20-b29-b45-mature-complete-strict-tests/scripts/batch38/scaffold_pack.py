#!/usr/bin/env python3
from pathlib import Path
import argparse, json, shutil
HERE=Path(__file__).resolve(); ROOT=HERE.parents[2]; T=ROOT/'templates/batch38'
p=argparse.ArgumentParser(); p.add_argument('--pack-key',required=True); p.add_argument('--output-root',default='deployment-lifecycle-packs'); a=p.parse_args()
out=Path(a.output_root)/a.pack_key; out.mkdir(parents=True,exist_ok=True)
for src in T.glob('*.json'):
 obj=json.loads(src.read_text()); raw=json.dumps(obj).replace('example-deployment-lifecycle',a.pack_key); obj=json.loads(raw)
 dest=out/('certification/'+src.name if src.name in ['evidence.json','certification.json'] else ('records/'+src.name if src.name not in ['pack.json','support-matrix.json','profile.json','candidates.json'] else src.name))
 dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(obj,indent=2)+'\n')
for d in ['corpus/development','corpus/negative','corpus/holdout','corpus/representative-workloads','certification','evidence/raw']:
 (out/d).mkdir(parents=True,exist_ok=True); (out/d/'.gitkeep').touch()
print(out)
