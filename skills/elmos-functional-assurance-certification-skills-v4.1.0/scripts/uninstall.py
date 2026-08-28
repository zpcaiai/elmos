#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo",required=True)
    args=ap.parse_args()
    repo=Path(args.repo).resolve()
    receipt_path=repo/".elmos/skillpacks/elmos-functional-assurance-certification-skills/install-receipt.json"
    if not receipt_path.is_file():
        print(json.dumps({"status":"BLOCKED","reason":f"receipt not found: {receipt_path}"},indent=2)); return 2
    receipt=json.loads(receipt_path.read_text())
    removed=[]; preserved=[]
    # Remove unchanged files only, deepest first.
    for row in sorted(receipt["files"],key=lambda r:len(Path(r["path"]).parts),reverse=True):
        p=Path(row["path"])
        if not p.exists(): continue
        if p.is_file() and sha256(p)==row["sha256"]:
            p.unlink(); removed.append(str(p))
        else:
            preserved.append(str(p))
    if receipt_path.exists(): receipt_path.unlink()
    # Prune empty directories under known roots.
    for base in [repo/".agents/skills",repo/".claude/skills",repo/".elmos/skillpacks/elmos-functional-assurance-certification-skills"]:
        if base.exists():
            for p in sorted((x for x in base.rglob("*") if x.is_dir()),key=lambda x:len(x.parts),reverse=True):
                try:p.rmdir()
                except OSError:pass
            try:base.rmdir()
            except OSError:pass
    restored=[]; blocked_restore=[]
    for b in reversed(receipt.get("backups",[])):
        dst=Path(b["destination"]); src=Path(b["backup"])
        if not src.exists(): continue
        if dst.exists():
            blocked_restore.append(str(dst)); continue
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.move(str(src),str(dst)); restored.append(str(dst))
    print(json.dumps({"status":"UNINSTALLED" if not preserved and not blocked_restore else "PARTIAL",
                      "removed":len(removed),"preservedModified":preserved,
                      "restored":restored,"blockedRestore":blocked_restore},indent=2))
    return 0 if not blocked_restore else 3

if __name__=="__main__":
    raise SystemExit(main())
