#!/usr/bin/env python3
import json, sys, hashlib, os
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def main():
    p=Path(sys.argv[1]); d=load(p); base=p.parent; errors=[]
    for item in d.get("files",[]):
        f=base/item["path"]
        if not f.exists(): errors.append(f"missing {f}"); continue
        if digest_file(f)!=item["sha256"]: errors.append(f"digest mismatch {f}")
    if errors: print("FAIL\n"+"\n".join(errors)); return 1
    print("PASS: evidence manifest matches files"); return 0
if __name__=="__main__": raise SystemExit(main())
