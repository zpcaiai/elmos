#!/usr/bin/env python3
from __future__ import annotations
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {"FILES.sha256"}

def main() -> int:
    lines = []
    for path in sorted(p for p in ROOT.rglob("*") if p.is_file()):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDE or "/__pycache__/" in f"/{rel}/" or rel.endswith(".pyc"):
            continue
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel}")
    (ROOT / "FILES.sha256").write_text("\n".join(lines) + "\n",encoding="utf-8")
    print(f"wrote {len(lines)} checksums")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
