#!/usr/bin/env python3
from pathlib import Path
import argparse, yaml
ap=argparse.ArgumentParser(); ap.add_argument('old'); ap.add_argument('new')
a=ap.parse_args()
def ids(root):
    obj=yaml.safe_load((Path(root)/'registry/skill-catalog.yaml').read_text(encoding='utf-8'))
    return {x['id']:x for x in obj['spec']['skills']}
o=ids(a.old); n=ids(a.new)
print('added',len(n.keys()-o.keys()))
for x in sorted(n.keys()-o.keys()): print('+',x)
print('removed',len(o.keys()-n.keys()))
for x in sorted(o.keys()-n.keys()): print('-',x)
print('common',len(o.keys()&n.keys()))
