#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from common import canonical_files, package_root, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    lines = []
    for path in canonical_files(root):
        rel = path.relative_to(root).as_posix()
        lines.append(f"{sha256_file(path)}  {rel}")
    (root / "CHECKSUMS.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} checksums")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
