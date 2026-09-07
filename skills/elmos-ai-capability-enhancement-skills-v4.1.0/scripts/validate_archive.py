#!/usr/bin/env python3
from __future__ import annotations
import argparse,io,tarfile,zipfile
from pathlib import PurePosixPath
import yaml

def safe(name):
 p=PurePosixPath(name);return not p.is_absolute() and '..' not in p.parts

def main():
 ap=argparse.ArgumentParser();ap.add_argument('archive');args=ap.parse_args();path=args.archive;names=[];manifest_bytes=None
 if path.endswith('.zip'):
  with zipfile.ZipFile(path) as z:
   names=z.namelist();bad=z.testzip()
   if bad:raise SystemExit(f'corrupt member {bad}')
   mf=[n for n in names if n.endswith('/package.yaml')]
   if len(mf)!=1:raise SystemExit('package.yaml inventory invalid')
   manifest_bytes=z.read(mf[0])
 else:
  with tarfile.open(path) as t:
   members=t.getmembers();names=[m.name for m in members]
   mf=[m for m in members if m.name.endswith('/package.yaml')]
   if len(mf)!=1:raise SystemExit('package.yaml inventory invalid')
   manifest_bytes=t.extractfile(mf[0]).read()
 if not all(safe(n) for n in names):raise SystemExit('unsafe archive path')
 expected=yaml.safe_load(manifest_bytes)['spec']['counts']
 skills=sum(n.endswith('/SKILL.md') and '/agent-skills/runtime/' in n for n in names)
 adapters=sum(n.endswith('/adapter.yaml') and '/target-adapters/' in n for n in names)
 routes=sum(n.endswith('/route.yaml') and '/golden-routes/' in n for n in names)
 if skills!=expected['skills'] or adapters!=expected['adapters'] or routes!=expected['goldenRoutes']:
  raise SystemExit(f"inventory mismatch skills={skills}/{expected['skills']} adapters={adapters}/{expected['adapters']} routes={routes}/{expected['goldenRoutes']}")
 print(f'PASS: {len(names)} members, {skills} component Skills, {adapters} adapters, {routes} Golden Routes')
if __name__=='__main__':main()
