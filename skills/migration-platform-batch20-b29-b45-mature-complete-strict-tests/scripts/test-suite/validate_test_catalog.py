#!/usr/bin/env python3
import json, sys, hashlib, os
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def main():
    p=Path(sys.argv[1] if len(sys.argv)>1 else "test-suites/batch1-37-strict/cases/catalog.json")
    d=load(p); cases=d.get("cases",[]); ids=[c.get("id") for c in cases]
    errors=[]
    if len(ids)!=len(set(ids)): errors.append("duplicate case ids")
    required={"id","skill","batches","capability","severity","test_type","title","preconditions","steps","assertions","evidence_required","anti_cheat"}
    for i,c in enumerate(cases):
        miss=required-set(c);
        if miss: errors.append(f"case {i} missing {sorted(miss)}")
        if c.get("severity") not in {"P0","P1","P2","P3"}: errors.append(f"{c.get('id')} invalid severity")
        if not c.get("anti_cheat"): errors.append(f"{c.get('id')} missing anti_cheat")
    if len(cases)<350: errors.append(f"catalog too small: {len(cases)}")
    if errors:
        print("FAIL"); print("\n".join(errors)); return 1
    print(f"PASS: {len(cases)} cases, unique ids, required fields present"); return 0
if __name__=="__main__": raise SystemExit(main())
