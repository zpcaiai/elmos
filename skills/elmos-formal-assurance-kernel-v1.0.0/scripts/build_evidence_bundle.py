#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"reference-kernel"))
from elmos_formal_assurance.evidence import write_manifest

def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("directory",type=Path)
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    output=args.output or args.directory/"evidence-manifest.json"
    manifest=write_manifest(args.directory,output)
    print(json.dumps({"output":str(output),"manifestSha256":manifest["manifestSha256"]},indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
