#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import load_manifest, package_root


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--format", choices=["mermaid", "dot"], default="mermaid")
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    manifest = load_manifest(root)
    skills = manifest["skills"]
    if args.format == "mermaid":
        print("flowchart TD")
        print("  start([Conversion Request])")
        for item in skills:
            name = item["name"].replace("-", "_")
            if not item["depends_on"]:
                print(f"  start --> {name}")
            for dep in item["depends_on"]:
                print(f"  {dep.replace('-', '_')} --> {name}")
    else:
        print("digraph skills {")
        print('  start [shape=oval,label="Conversion Request"];')
        for item in skills:
            name = item["name"].replace("-", "_")
            print(f'  {name} [label="{item["name"]}"];')
            if not item["depends_on"]:
                print(f"  start -> {name};")
            for dep in item["depends_on"]:
                print(f"  {dep.replace('-', '_')} -> {name};")
        print("}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
