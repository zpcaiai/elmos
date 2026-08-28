#!/usr/bin/env python3
from __future__ import annotations
import argparse, gzip, hashlib, os, tarfile, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT.parent
FIXED=(2026,8,28,0,0,0)
EXCLUDE_NAMES={".DS_Store"}
EXCLUDE_PARTS={"__pycache__",".git",".pytest_cache"}
EXCLUDE_FILES={"CONTROLLED_FILES.sha256"}

def files():
    out=[]
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT)
        if p.name in EXCLUDE_NAMES or any(part in EXCLUDE_PARTS for part in rel.parts): continue
        if p.name in EXCLUDE_FILES: continue
        out.append((p,rel))
    return sorted(out,key=lambda x:x[1].as_posix())

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def write_controlled():
    rows=[f"{digest(p)}  {rel.as_posix()}" for p,rel in files()]
    (ROOT/"CONTROLLED_FILES.sha256").write_text("\n".join(rows)+"\n",encoding="utf-8")

def all_archive_files():
    out=[]
    for p in ROOT.rglob("*"):
        if not p.is_file(): continue
        rel=p.relative_to(ROOT)
        if p.name in EXCLUDE_NAMES or any(part in EXCLUDE_PARTS for part in rel.parts): continue
        out.append((p,rel))
    return sorted(out,key=lambda x:x[1].as_posix())

def build_zip(path):
    prefix=ROOT.name
    with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p,rel in all_archive_files():
            zi=zipfile.ZipInfo(f"{prefix}/{rel.as_posix()}",FIXED)
            zi.external_attr=(p.stat().st_mode & 0xFFFF)<<16
            z.writestr(zi,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)

def build_tar(path):
    prefix=ROOT.name
    # Control both the gzip header and each tar member for byte-for-byte reproducibility.
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="",mode="wb",fileobj=raw,compresslevel=9,mtime=1787875200) as gz:
            with tarfile.open(fileobj=gz,mode="w",format=tarfile.PAX_FORMAT) as t:
                for p,rel in all_archive_files():
                    ti=t.gettarinfo(str(p),arcname=f"{prefix}/{rel.as_posix()}")
                    ti.mtime=1787875200
                    ti.uid=0;ti.gid=0;ti.uname="";ti.gname=""
                    with p.open("rb") as f:t.addfile(ti,f)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out-dir",default=str(PARENT))
    args=ap.parse_args()
    out=Path(args.out_dir);out.mkdir(parents=True,exist_ok=True)
    write_controlled()
    zip_path=out/f"{ROOT.name}.zip"
    tar_path=out/f"{ROOT.name}.tar.gz"
    build_zip(zip_path);build_tar(tar_path)
    sums=out/f"{ROOT.name}-SHA256SUMS.txt"
    sums.write_text(f"{digest(zip_path)}  {zip_path.name}\n{digest(tar_path)}  {tar_path.name}\n",encoding="utf-8")
    print(zip_path);print(tar_path);print(sums)

if __name__=="__main__":
    main()
