#!/usr/bin/env python3
import json, sys, hashlib, os
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else "test-suites/batch1-37-strict")
    cat=load(root/"cases/catalog.json")
    out={"catalog_sha256":digest_file(root/"cases/catalog.json"),"case_count":len(cat["cases"]),"case_ids":[c["id"] for c in cat["cases"]]}
    (root/"cases/manifest.json").write_text(json.dumps(out,indent=2)+"\n")
    print(f"WROTE {root/'cases/manifest.json'}")
if __name__=="__main__": raise SystemExit(main())
