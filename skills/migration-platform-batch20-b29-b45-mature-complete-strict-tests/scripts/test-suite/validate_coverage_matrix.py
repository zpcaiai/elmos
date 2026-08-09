#!/usr/bin/env python3
import json, sys, hashlib, os
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def main():
    p=Path(sys.argv[1] if len(sys.argv)>1 else "test-suites/batch1-37-strict/coverage-matrix.json")
    d=load(p); batches=d.get("batches",{}); errors=[]
    for b in range(1,38):
        ids=batches.get(str(b),[])
        if len(ids)<8: errors.append(f"Batch {b} has {len(ids)} cases; need >=8")
    if len(d.get("cross_cutting",[]))<10: errors.append("need >=10 cross-cutting skills")
    if errors: print("FAIL\n"+"\n".join(errors)); return 1
    print("PASS: Batch 1-37 coverage complete"); return 0
if __name__=="__main__": raise SystemExit(main())
