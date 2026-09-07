#!/usr/bin/env python3
from __future__ import annotations
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main() -> int:
    env=dict(__import__("os").environ)
    env["PYTHONPATH"]=str(ROOT/"reference-kernel")
    checks=[
      [sys.executable,"scripts/generate_catalog.py"],
      [sys.executable,"scripts/validate_package.py"],
      [sys.executable,"scripts/generate_checksums.py"],
    ]
    for command in checks:
        result=subprocess.run(command,cwd=ROOT,env=env)
        if result.returncode:
            return result.returncode
    for p in ROOT.rglob("__pycache__"):
        shutil.rmtree(p,ignore_errors=True)
    for p in ROOT.rglob("*.pyc"):
        p.unlink(missing_ok=True)
    output=ROOT.parent/f"{ROOT.name}.zip"
    output.unlink(missing_ok=True)
    shutil.make_archive(str(output.with_suffix("")),"zip",root_dir=ROOT.parent,base_dir=ROOT.name)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    sha_file=ROOT.parent/f"{output.name}.sha256"
    sha_file.write_text(f"{digest}  {output.name}\n",encoding="utf-8")
    print(f"{output}\n{sha_file}\nsha256={digest}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
