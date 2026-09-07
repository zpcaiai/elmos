#!/usr/bin/env python3
"""Additive local installation; dry-run by default. Trusted local filesystem only."""
import argparse,hashlib,json,os,shutil,tempfile,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1];NAME='elmos-ai-optimization';PACKAGE='elmos-ai-optimization-skills';RECEIPT='.installation-receipt.json'

def safe(root,rel):
    p=PurePosixPath(rel)
    if not rel or p.is_absolute() or '..' in p.parts or '\\' in rel or '\x00' in rel or str(p)!=rel:raise ValueError('unsafe path')
    for i in range(1,len(p.parts)+1):
        if root.joinpath(*p.parts[:i]).is_symlink():raise ValueError('symlink refused')
    return root.joinpath(*p.parts)

def inventory(root):
    return {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not p.name.endswith('.pyc') and p.name not in ['FILES.sha256',RECEIPT]}

def manifest(source):
    m=source/'FILES.sha256'
    if not m.is_file():raise ValueError('package not sealed')
    files={}
    for line in m.read_text().splitlines():
        h,rel=line.split('  ',1);p=safe(source,rel)
        if rel in files or len(h)!=64 or not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:raise ValueError('hash mismatch '+rel)
        files[rel]=h
    if set(files)!=inventory(source):raise ValueError('unlisted/missing files')
    files['FILES.sha256']=hashlib.sha256(m.read_bytes()).hexdigest();return files

def run(repo,source=ROOT,apply=False,uninstall=False):
    if repo.is_symlink() or not repo.is_dir():raise ValueError('existing non-symlink repository required')
    repo=repo.resolve();source=source.resolve();files=manifest(source);dest=safe(repo,'.agents/skills/'+NAME)
    if not uninstall and (dest==source or source in dest.parents):raise ValueError('source and destination must be independent')
    result=dict(operation='uninstall' if uninstall else 'install',apply=apply,destination=str(dest),files=len(files),changes_to_AGENTS=False)
    if uninstall:
        rp=safe(dest,RECEIPT)
        if not rp.is_file():raise ValueError('receipt required')
        receipt=json.loads(rp.read_text())
        if receipt.get('package')!=PACKAGE or receipt.get('files')!=files:raise ValueError('receipt/version mismatch')
        remove=[];preserve=[]
        for rel,h in files.items():
            p=safe(dest,rel)
            if p.is_file():(remove if hashlib.sha256(p.read_bytes()).hexdigest()==h else preserve).append(rel)
        result.update(remove=remove,preserve_modified=preserve)
        if apply:
            for rel in remove:safe(dest,rel).unlink()
            rp.unlink()
            for p in sorted(dest.rglob('*'),key=lambda p:len(p.parts),reverse=True):
                if p.is_dir() and not p.is_symlink():
                    try:p.rmdir()
                    except OSError:pass
            try:dest.rmdir()
            except OSError:pass
        return result
    if dest.exists():
        rp=safe(dest,RECEIPT)
        if all(safe(dest,r).is_file() and hashlib.sha256(safe(dest,r).read_bytes()).hexdigest()==h for r,h in files.items()) and rp.is_file() and json.loads(rp.read_text()).get('files')==files:result['status']='already_installed';return result
        raise FileExistsError('existing skill preserved; no overwrite')
    result['status']='planned'
    if not apply:return result
    dest.parent.mkdir(parents=True,exist_ok=True);lock=safe(repo,'.agents/.elmos-ai-optimization-install.lock')
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);stage=None
    try:
        if dest.exists():raise FileExistsError('destination appeared')
        stage=Path(tempfile.mkdtemp(prefix='.aiopt-',dir=dest.parent))
        for rel in files:
            p=safe(stage,rel);p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(safe(source,rel),p)
        (stage/RECEIPT).write_text(json.dumps(dict(package=PACKAGE,files=files),indent=2));stage.rename(dest);stage=None;result['status']='installed'
    finally:
        if stage is not None:shutil.rmtree(stage)
        lock.unlink(missing_ok=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);p.add_argument('--apply',action='store_true');p.add_argument('--uninstall',action='store_true');a=p.parse_args()
    try:print(json.dumps(run(a.repo,apply=a.apply,uninstall=a.uninstall),ensure_ascii=False,indent=2))
    except (ValueError,OSError,KeyError) as e:print(json.dumps({'status':'blocked','reason':str(e)},ensure_ascii=False));sys.exit(2)
