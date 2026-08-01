#!/usr/bin/env python3
from pathlib import Path
import argparse, shutil, json

ROOT = Path(__file__).resolve().parent

def parse_batches(text):
    if not text:
        return None
    result=set()
    for part in text.split(','):
        part=part.strip()
        if '-' in part:
            a,b=part.split('-',1)
            result.update(range(int(a), int(b)+1))
        else:
            result.add(int(part))
    return result

p=argparse.ArgumentParser()
p.add_argument('--target', required=True)
p.add_argument('--batches', default='')
p.add_argument('--include-batch-orchestrators', action='store_true')
p.add_argument('--overwrite', action='store_true')
a=p.parse_args()
target=Path(a.target).expanduser().resolve(); target.mkdir(parents=True, exist_ok=True)
selected=parse_batches(a.batches)
installed=[]
for bdir in sorted((ROOT/'batches').glob('batch-*')):
    num=int(bdir.name.split('-')[1])
    if selected and num not in selected: continue
    for sdir in sorted((bdir/'skills').iterdir()):
        if not sdir.is_dir(): continue
        dst=target/sdir.name
        if dst.exists():
            if not a.overwrite: raise SystemExit(f'exists: {dst}; use --overwrite')
            shutil.rmtree(dst)
        shutil.copytree(sdir,dst); installed.append(sdir.name)
    if a.include_batch_orchestrators:
        dst=target/bdir.name
        if dst.exists():
            if not a.overwrite: raise SystemExit(f'exists: {dst}; use --overwrite')
            shutil.rmtree(dst)
        dst.mkdir(); shutil.copy2(bdir/'SKILL.md',dst/'SKILL.md'); installed.append(bdir.name)
meta_src=ROOT/'meta'/'precision-migration-orchestrator'
meta_dst=target/meta_src.name
if meta_dst.exists() and a.overwrite: shutil.rmtree(meta_dst)
if not meta_dst.exists(): shutil.copytree(meta_src,meta_dst); installed.append(meta_src.name)
print(json.dumps({'target':str(target),'installed_count':len(installed),'installed':installed},ensure_ascii=False,indent=2))
