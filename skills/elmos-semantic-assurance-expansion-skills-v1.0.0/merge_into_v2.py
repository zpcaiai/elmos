#!/usr/bin/env python3
from pathlib import Path
import argparse,json,shutil
p=argparse.ArgumentParser(); p.add_argument('v2'); p.add_argument('out'); a=p.parse_args(); src=Path(a.v2); dst=Path(a.out); root=Path(__file__).resolve().parent
if dst.exists(): shutil.rmtree(dst)
shutil.copytree(src,dst)
base=json.loads((dst/'manifest.json').read_text()); inc=json.loads((root/'manifest.json').read_text())
if len(base.get('skills',[]))!=168: raise SystemExit('expected a 168-Skill v2 base')
for e in inc['skills']:
 s=root/e['path']; d=dst/e['path']; d.parent.mkdir(parents=True,exist_ok=True); shutil.copytree(s,d)
base['skills']+=inc['skills']; base['package']['version']='3.0.0'; base['package']['skill_count']=300; base['package']['semantic_assurance_skill_count']=132; base['package']['certification_route_count']=40
(dst/'manifest.json').write_text(json.dumps(base,indent=2,ensure_ascii=False)+'\n')
for name in ['schemas','policies','templates','references','certification-corpus','native-runtime-lab','scripts']:
 if (root/name).exists(): shutil.copytree(root/name,dst/name,dirs_exist_ok=True)
for f in ['route-certification-registry.json']:
 shutil.copy2(root/f,dst/f)
print(dst)
