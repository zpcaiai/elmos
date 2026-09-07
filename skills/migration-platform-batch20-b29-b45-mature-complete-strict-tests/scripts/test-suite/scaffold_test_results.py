#!/usr/bin/env python3
import json, sys, hashlib, os
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else "test-suites/batch1-37-strict")
    cat=load(root/"cases/catalog.json"); res=root/"results"; res.mkdir(parents=True,exist_ok=True)
    for c in cat["cases"]:
        p=res/f"{c['id']}.json"
        if not p.exists():
            p.write_text(json.dumps({"case_id":c["id"],"status":"not-run","artifact_digest":"sha256:"+"0"*64,"environment_digest":"sha256:"+"0"*64,"started_at":"","finished_at":"","evidence":[]},indent=2)+"\n")
    print(f"WROTE {len(cat['cases'])} result placeholders")
if __name__=="__main__": raise SystemExit(main())
