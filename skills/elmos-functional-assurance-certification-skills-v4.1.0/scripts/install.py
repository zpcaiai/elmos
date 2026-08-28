#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,shutil,time
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
PACKAGE="elmos-functional-assurance-certification-skills";VERSION="4.1.0";SHARED_SLUG="elmos-functional-assurance-certification-skills"
BASE_REQUIRED=True
BASE_RECEIPT_REL=Path('.elmos/skillpacks/elmos-ai-capability-enhancement-skills/install-receipt.json')
SHARED_DIRS=['catalog','contracts','target-adapters','workflows','policies','database','implementation','golden-routes','templates','examples','docs','reference_kernel','native-fixtures']
SHARED_FILES=['package.yaml','README.md','CHANGELOG.md','REFERENCES.md','SKILL.md','PACKAGE_RELATIONSHIP.md']
def sha256(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def registry():return yaml.safe_load((ROOT/'catalog/skill-registry.yaml').read_text())['spec']['skills']
def select(profile,rows):
 by={r['name']:r for r in rows}
 if profile=='all':seeds=set(by)
 elif profile=='p0':seeds={n for n,r in by.items() if r['priority']=='P0'}
 else:
  groups={'specification','planning','semantic-ir','certification','certification-authority','certification-scheme','lab-competence'}
  seeds={n for n,r in by.items() if r['group'] in groups}
 changed=True
 while changed:
  changed=False
  for n in list(seeds):
   for d in by[n].get('depends_on',[]):
    if d not in seeds:seeds.add(d);changed=True
 return [by[n] for n in sorted(seeds)]
def cp_tree(src,dst,installed):
 for p in src.rglob('*'):
  rel=p.relative_to(src);o=dst/rel
  if p.is_dir():o.mkdir(parents=True,exist_ok=True)
  elif p.is_file() and '__pycache__' not in rel.parts:
   o.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,o);installed.append({'path':str(o),'sha256':sha256(o)})
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True);ap.add_argument('--host',choices=['codex','claude','both'],default='both');ap.add_argument('--profile',choices=['core','p0','all'],default='p0');ap.add_argument('--dry-run',action='store_true');ap.add_argument('--force',action='store_true');ap.add_argument('--allow-missing-base',action='store_true');args=ap.parse_args()
 repo=Path(args.repo).resolve();base_ok=(repo/BASE_RECEIPT_REL).is_file()
 if BASE_REQUIRED and not base_ok and not args.allow_missing_base:
  print(json.dumps({'status':'BLOCKED','reason':'capability base package receipt missing','expected':str(repo/BASE_RECEIPT_REL),'override':'--allow-missing-base'},indent=2));return 2
 rows=registry();sel=select(args.profile,rows);hosts=[]
 if args.host in ('codex','both'):hosts.append(repo/'.agents/skills')
 if args.host in ('claude','both'):hosts.append(repo/'.claude/skills')
 shared=repo/'.elmos/skillpacks'/SHARED_SLUG;conf=[]
 for b in hosts:
  for r in sel:
   if (b/r['name']).exists():conf.append(str(b/r['name']))
 if shared.exists():conf.append(str(shared))
 plan={'package':PACKAGE,'version':VERSION,'repo':str(repo),'skills':[r['name'] for r in sel],'baseReceiptPresent':base_ok,'conflicts':conf}
 if args.dry_run:print(json.dumps(plan,indent=2));return 0
 if conf and not args.force:print(json.dumps({'status':'BLOCKED','conflicts':conf},indent=2));return 2
 stamp=time.strftime('%Y%m%d-%H%M%S');backups=[];backup_root=repo/'.elmos/install-backups'/stamp
 if args.force:
  for x in conf:
   src=Path(x);dst=backup_root/src.relative_to(repo);dst.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(src),str(dst));backups.append({'destination':str(src),'backup':str(dst)})
 installed=[]
 for b in hosts:
  b.mkdir(parents=True,exist_ok=True)
  for r in sel:cp_tree(ROOT/'agent-skills/runtime'/r['name'],b/r['name'],installed)
 shared.mkdir(parents=True,exist_ok=True)
 for d in SHARED_DIRS:cp_tree(ROOT/d,shared/d,installed)
 for f in SHARED_FILES:
  o=shared/f;o.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f,o);installed.append({'path':str(o),'sha256':sha256(o)})
 receipt={'package':PACKAGE,'version':VERSION,'installedAt':stamp,'skills':[r['name'] for r in sel],'files':installed,'backups':backups,'baseReceiptPresent':base_ok}
 rp=shared/'install-receipt.json';rp.write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps({'status':'INSTALLED','skills':len(sel),'files':len(installed),'receipt':str(rp)},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
