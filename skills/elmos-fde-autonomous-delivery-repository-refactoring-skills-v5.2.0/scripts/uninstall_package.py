#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil, sys
from pathlib import Path

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024), b""): h.update(chunk)
    return h.hexdigest()

def latest_receipt(repo: Path, package: str) -> Path | None:
    paths=sorted((repo/".elmos/install-receipts").glob(f"{package}-*.json"))
    paths=[p for p in paths if not p.name.endswith(".uninstalled.json")]
    return paths[-1] if paths else None

def prune(path: Path, stop: Path) -> None:
    cur=path
    while cur != stop and cur.exists():
        try: cur.rmdir()
        except OSError: break
        cur=cur.parent

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--repo", required=True); p.add_argument("--receipt"); args=p.parse_args()
    package=Path(__file__).resolve().parents[1]; repo=Path(args.repo).resolve()
    receipt=Path(args.receipt).resolve() if args.receipt else latest_receipt(repo,package.name)
    if not receipt or not receipt.exists(): print("receipt not found",file=sys.stderr); return 2
    data=json.loads(receipt.read_text(encoding="utf-8")); removed=[]; preserved=[]; restored=[]
    for entry in reversed(data["entries"]):
        dst=repo/entry["path"]
        if entry["action"] in {"install", "replace"} and dst.exists():
            if dst.is_file() and sha(dst)==entry["installedHash"]:
                dst.unlink(); removed.append(entry["path"]); prune(dst.parent,repo)
            else: preserved.append(entry["path"])
        backup=entry.get("backup")
        if backup and not dst.exists():
            src=repo/backup; dst.parent.mkdir(parents=True,exist_ok=True)
            if src.exists():
                if src.is_dir(): shutil.copytree(src,dst)
                else: shutil.copy2(src,dst)
                restored.append(entry["path"])
    out=receipt.with_name(receipt.stem+".uninstalled.json"); receipt.rename(out)
    print(json.dumps({"status":"UNINSTALLED","removed":len(removed),"preservedModified":preserved,"restored":restored,"receipt":str(out)},indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())
