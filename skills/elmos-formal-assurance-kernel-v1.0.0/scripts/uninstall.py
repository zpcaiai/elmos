#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
from pathlib import Path

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("target",type=Path)
    p.add_argument("--dry-run",action="store_true")
    args=p.parse_args()
    target=args.target.resolve()
    manifest_path=target/".elmos/formal-assurance-install-manifest.json"
    if not manifest_path.is_file():
        print(f"install manifest not found: {manifest_path}")
        return 2
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    modified=[]
    removed=0
    restored=0
    for entry in reversed(manifest["files"]):
        dst=target/entry["destination"]
        if not dst.exists():
            continue
        if not dst.is_file() or sha(dst)!=entry["sha256"]:
            modified.append(entry["destination"])
            continue
        if args.dry_run:
            print(f"remove: {entry['destination']}")
            continue
        dst.unlink()
        removed+=1
        backup=entry.get("backup")
        if backup:
            source=target/backup
            if source.is_file():
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,dst)
                restored+=1

    if modified:
        print("Preserved files modified after installation:")
        print("\n".join(modified))
    if args.dry_run:
        return 0
    if not modified:
        manifest_path.unlink(missing_ok=True)
    # Remove empty directories below well-known roots only.
    for base in ["skills/formal-assurance-kernel","contracts/formal-assurance","workflows/formal-assurance",
                 "policies/formal-assurance","verifier-adapters/formal-assurance",
                 "reference/formal-assurance-kernel","golden-routes/formal-assurance","docs/formal-assurance"]:
        d=target/base
        if d.exists():
            for child in sorted((x for x in d.rglob("*") if x.is_dir()),reverse=True):
                try: child.rmdir()
                except OSError: pass
            try: d.rmdir()
            except OSError: pass
    print(f"removed {removed}, restored {restored}, preserved modified {len(modified)}")
    return 1 if modified else 0

if __name__=="__main__":
    raise SystemExit(main())
