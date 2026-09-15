#!/usr/bin/env python3
from pathlib import Path
import argparse, shutil, json, sys
p=argparse.ArgumentParser()
p.add_argument('--repo',required=True)
p.add_argument('--agent',choices=['codex','antigravity','both'],default='codex')
p.add_argument('--apply',action='store_true')
a=p.parse_args()
repo=Path(a.repo).expanduser()
if not repo.is_absolute() or not repo.exists() or not repo.is_dir():
    print(json.dumps({'status':'BLOCKED','reason':'REPO_MUST_BE_EXISTING_ABSOLUTE_DIRECTORY'})); sys.exit(2)
src=Path(__file__).resolve().parents[1]/'agent-skills'
targets=[]
if a.agent in ('codex','both'): targets.append(repo/'.agents'/'skills')
if a.agent in ('antigravity','both'): targets.append(repo/'.antigravity'/'skills')
ops=[]
for target in targets:
    for skill in src.iterdir():
        if skill.is_dir(): ops.append((skill,target/skill.name))
if not a.apply:
    print(json.dumps({'status':'DRY_RUN','operations':[{'from':str(s),'to':str(t)} for s,t in ops]},indent=2)); sys.exit(0)
for s,t in ops:
    t.parent.mkdir(parents=True,exist_ok=True)
    if t.exists(): shutil.rmtree(t)
    shutil.copytree(s,t)
print(json.dumps({'status':'INSTALLED','count':len(ops),'agent':a.agent},indent=2))
