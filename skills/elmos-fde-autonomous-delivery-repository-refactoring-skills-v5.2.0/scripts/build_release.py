#!/usr/bin/env python3
from __future__ import annotations
import argparse, gzip, hashlib, os, shutil, stat, tarfile, tempfile, zipfile
from pathlib import Path

EXCLUDE={"__pycache__", ".DS_Store"}
def included(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file(): continue
        if any(x in EXCLUDE for x in p.parts) or p.suffix==".pyc" or p.name=="CONTROLLED_FILES.sha256": continue
        yield p
def digest(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for c in iter(lambda:f.read(1024*1024),b""): h.update(c)
    return h.hexdigest()
def controlled(root: Path):
    lines=[f"{digest(p)}  {p.relative_to(root).as_posix()}" for p in included(root)]
    (root/"CONTROLLED_FILES.sha256").write_text("\n".join(lines)+"\n",encoding="utf-8")
def files(root: Path):
    return [p for p in sorted(root.rglob("*")) if p.is_file() and not any(x in EXCLUDE for x in p.parts) and p.suffix!=".pyc"]
def make_zip(root: Path, out: Path):
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in files(root):
            arc=f"{root.name}/{p.relative_to(root).as_posix()}"; info=zipfile.ZipInfo(arc,(1980,1,1,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            mode=0o755 if os.access(p,os.X_OK) else 0o644; info.external_attr=(stat.S_IFREG|mode)<<16
            z.writestr(info,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
def make_tgz(root: Path,out: Path):
    with out.open("wb") as raw:
        with gzip.GzipFile(filename="",mode="wb",fileobj=raw,compresslevel=9,mtime=0) as gz:
            with tarfile.open(mode="w",fileobj=gz,format=tarfile.PAX_FORMAT) as t:
                for p in files(root):
                    arc=f"{root.name}/{p.relative_to(root).as_posix()}"; info=t.gettarinfo(str(p),arcname=arc)
                    info.uid=0; info.gid=0; info.uname=""; info.gname=""; info.mtime=0; info.mode=0o755 if os.access(p,os.X_OK) else 0o644
                    with p.open("rb") as f:t.addfile(info,f)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("root",nargs="?",default="."); ap.add_argument("--output-dir",default="../release"); args=ap.parse_args()
    root=Path(args.root).resolve(); out=Path(args.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True); controlled(root)
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); z1=td/"a.zip"; z2=td/"b.zip"; t1=td/"a.tar.gz"; t2=td/"b.tar.gz"
        make_zip(root,z1); make_zip(root,z2); make_tgz(root,t1); make_tgz(root,t2)
        if digest(z1)!=digest(z2) or digest(t1)!=digest(t2): raise SystemExit("non-deterministic archive build")
        zfinal=out/f"{root.name}.zip"; tfinal=out/f"{root.name}.tar.gz"; shutil.copy2(z1,zfinal); shutil.copy2(t1,tfinal)
    hashes=f"{digest(zfinal)}  {zfinal.name}\n{digest(tfinal)}  {tfinal.name}\n"; (out/"RELEASE_HASHES.txt").write_text(hashes,encoding="utf-8")
    print(hashes,end="")
if __name__=="__main__": main()
