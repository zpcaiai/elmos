#!/usr/bin/env python3
import json, sys, hashlib, os
from pathlib import Path

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def digest_file(path):
    h=hashlib.sha256(); h.update(Path(path).read_bytes()); return h.hexdigest()

import re
def main():
    root=Path(sys.argv[1] if len(sys.argv)>1 else ".")
    files=sorted((root/".agents/skills").glob("tst-*/SKILL.md")); errors=[]; names=[]
    for f in files:
        t=f.read_text(encoding="utf-8")
        m=re.search(r"^name:\s*(\S+)",t,re.M)
        if not m: errors.append(f"missing name {f}"); continue
        names.append(m.group(1))
        for h in ["## Workflow","## Verification","## Stop and escalate when","## Definition of done"]:
            if h not in t: errors.append(f"{f} missing {h}")
    if len(names)!=len(set(names)): errors.append("duplicate skill names")
    if len(files)<52: errors.append(f"need 52 skills, found {len(files)}")
    if errors: print("FAIL\n"+"\n".join(errors)); return 1
    print(f"PASS: {len(files)} strict test skills") ; return 0
if __name__=="__main__": raise SystemExit(main())
