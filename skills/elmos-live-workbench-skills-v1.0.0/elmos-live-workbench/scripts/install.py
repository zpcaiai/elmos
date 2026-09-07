#!/usr/bin/env python3
"""Non-overwriting local installer. Default is dry run. No network, git or global edits."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,sys,tempfile
from pathlib import Path
PACKAGE=Path(__file__).resolve().parents[1]
NAME='elmos-live-workbench'
PAYLOAD=Path('.elmos/skillpacks')/NAME
ROUTER=Path('.agents/skills')/NAME
RECEIPT=Path('.elmos/install-receipts')/(NAME+'.json')

def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def guarded(root:Path,rel:Path)->Path:
    if rel.is_absolute() or '..' in rel.parts:raise ValueError('unsafe destination')
    cur=root
    for part in rel.parts:
        cur=cur/part
        if cur.is_symlink():raise ValueError('symlink destination rejected: '+str(cur))
    return cur

def router_text()->str:
    return """---
name: elmos-live-workbench
description: 为 Elmos 生成和转换项目实现证据化源码教学、真实调试与 READY 后600秒预览；按增量能力包路由，不复制现有内核。
---

# Elmos Live Workbench
从当前仓库根目录读取 `.elmos/skillpacks/elmos-live-workbench/SKILL.md`，再读同目录
`INTEGRATION.md`、`IMPLEMENTATION_PLAN.md` 和 `SKILL_INDEX.md`。
内部28个工作流只按需读取，不注册为28个新的全局路由。
不得把本包参考测试通过当作生产隔离或真实600秒验收通过。不得自签E5。
"""

def install(repo:Path,apply:bool=False)->dict:
    repo=repo.resolve(strict=True)
    dest=guarded(repo,PAYLOAD);router=guarded(repo,ROUTER);receipt=guarded(repo,RECEIPT)
    for p in [dest,router,receipt]:
        if p.exists():raise FileExistsError('refuse to overwrite existing path: '+str(p))
    plan={'operation':'install','apply':apply,'payload':str(dest),'router':str(router),'receipt':str(receipt),'compatibility':'live repository implementation not verified'}
    if not apply:return plan
    # Unique dedicated directories only; clean up our own partial writes on failure.
    made=[]
    try:
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.mkdir(exist_ok=False);made.append(dest)
        shutil.copytree(PACKAGE,dest,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.DS_Store'))
        router.mkdir(parents=True,exist_ok=False);made.append(router)
        (router/'SKILL.md').write_text(router_text(),encoding='utf-8')
        files={str(p.relative_to(repo)):sha(p) for base in [dest,router] for p in base.rglob('*') if p.is_file()}
        data={'name':NAME,'version':'1.0.0','files':files,'roots':[str(PAYLOAD),str(ROUTER)]}
        receipt.parent.mkdir(parents=True,exist_ok=True)
        with receipt.open('x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2)
        plan['files_installed']=len(files)
        return plan
    except BaseException:
        for p in reversed(made):shutil.rmtree(p,ignore_errors=True)
        raise

def uninstall(repo:Path,apply:bool=False)->dict:
    repo=repo.resolve(strict=True);receipt=guarded(repo,RECEIPT)
    data=json.loads(receipt.read_text());remove=[];preserve=[]
    allowed=[PAYLOAD,ROUTER]
    for rel,expected in data['files'].items():
        relative=Path(rel)
        if not any(relative.is_relative_to(a) for a in allowed):raise ValueError('receipt path outside package roots')
        p=guarded(repo,relative)
        if p.is_file() and sha(p)==expected:remove.append(p)
        elif p.exists():preserve.append(str(relative))
    if apply:
        for p in remove:p.unlink()
        for base in allowed:
            root=guarded(repo,base)
            if root.exists():
                for d in sorted((x for x in root.rglob('*') if x.is_dir()),key=lambda x:len(x.parts),reverse=True):
                    try:d.rmdir()
                    except OSError:pass
                try:root.rmdir()
                except OSError:pass
        receipt.unlink()
    return {'operation':'uninstall','apply':apply,'matching_files':len(remove),'preserved_modified_files':preserve,'note':'untracked files and changed files are never deleted'}

def main():
    a=argparse.ArgumentParser();a.add_argument('--repo',type=Path,required=True);a.add_argument('--apply',action='store_true');a.add_argument('--uninstall',action='store_true');args=a.parse_args()
    try:
        result=(uninstall if args.uninstall else install)(args.repo,args.apply)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,KeyError) as e:
        print(json.dumps({'status':'refused','reason':str(e)},ensure_ascii=False),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
