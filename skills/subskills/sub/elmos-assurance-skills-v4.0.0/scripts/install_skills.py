#!/usr/bin/env python3
"""Explicit local install, dry-run by default, refuses overwrites and symlinks."""
from __future__ import annotations
import argparse, json, os, shutil, tempfile
from pathlib import Path
from validate_package import manifest_files
ROOT=Path(__file__).resolve().parents[1]
PACKAGE_DIR='assurance-package-v4.0.0'

def safe_destination(repo:Path,rel:Path):
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('UNSAFE_DESTINATION')
    p=repo
    for part in rel.parts:
        p=p/part
        if p.is_symlink():raise ValueError('SYMLINK_DESTINATION:'+str(p))
        if p.exists() and not p.is_dir():raise ValueError('NON_DIRECTORY_DESTINATION:'+str(p))
    return p

def install(repo:Path,agent:str,apply:bool=False):
    if agent not in {'codex','claude'}:raise ValueError('UNKNOWN_AGENT')
    if not repo.is_absolute() or not repo.is_dir() or repo.is_symlink():raise ValueError('REPO_MUST_BE_EXISTING_ABSOLUTE_DIRECTORY')
    repo=repo.resolve()
    if not (repo/'.git').exists():raise ValueError('EXPECTED_EXISTING_GIT_REPOSITORY')
    if repo==ROOT or repo.is_relative_to(ROOT):raise ValueError('DO_NOT_INSTALL_IN_PACKAGE')
    files=manifest_files(ROOT)
    skill_root=Path('.agents/skills'if agent=='codex'else'.claude/skills')
    names=sorted(p.name for p in (ROOT/'skills').iterdir()if p.is_dir())
    destinations=[Path('.elmos')/PACKAGE_DIR]+[skill_root/n for n in names]
    for rel in destinations:
        p=safe_destination(repo,rel)
        if p.exists():raise ValueError('REFUSE_OVERWRITE:'+str(rel))
    report={'mode':'APPLY'if apply else'DRY_RUN','repo':str(repo),'agent':agent,'skill_count':len(names),'package_file_count':len(files)+1,'destinations':[str(p)for p in destinations],'executes_repository_code':False,'changes_agent_policy_file':False}
    if not apply:return report
    lock=repo/'.elmos-assurance-install.lock'
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600);os.close(fd)
    created=[]
    try:
        with tempfile.TemporaryDirectory(prefix='.elmos-assurance-stage-',dir=repo)as temp:
            stage=Path(temp);pkg=stage/'package';pkg.mkdir()
            for name in list(files)+['PACKAGE_CONTENTS.sha256']:
                src=ROOT/name;target=pkg/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,target,follow_symlinks=False)
            manifest_files(pkg)
            for rel in destinations:
                p=safe_destination(repo,rel)
                if p.exists():raise ValueError('DESTINATION_CHANGED:'+str(rel))
                p.parent.mkdir(parents=True,exist_ok=True)
            # The copy stage contains no executed hooks. Publishing uses same-filesystem renames.
            for name in names:
                src=stage/name;shutil.copytree(pkg/'skills'/name,src)
                dest=repo/skill_root/name;src.rename(dest);created.append(dest)
            dest=repo/'.elmos'/PACKAGE_DIR;pkg.rename(dest);created.append(dest)
    except Exception:
        for p in reversed(created):shutil.rmtree(p)
        raise
    finally:lock.unlink(missing_ok=True)
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repo',required=True,type=Path);ap.add_argument('--agent',choices=['codex','claude'],default='codex');ap.add_argument('--apply',action='store_true');a=ap.parse_args()
    try:print(json.dumps(install(a.repo,a.agent,a.apply),ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError)as exc:print(json.dumps({'status':'BLOCKED','reason':str(exc)},ensure_ascii=False));return 2
if __name__=='__main__':raise SystemExit(main())
