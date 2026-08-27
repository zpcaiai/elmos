#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = (
    "REPLACE_WITH_SIGNED_DIGEST",
    "REPLACE_WITH_RELEASE_TIME_PINNED_DIGEST",
    "REPLACE_WITH_RELEASE_TIME_PINNED_TAG",
    "REPLACE_WITH_PINNED_COMMIT",
)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict",action="store_true")
    args = parser.parse_args()
    findings=[]
    for p in ROOT.rglob("*"):
        if not p.is_file() or ".git" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            text=p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in TOKENS:
            if token in text:
                findings.append(f"{p.relative_to(ROOT)}: {token}")
    if findings:
        print("Release-time pins required:")
        print("\n".join(findings))
        return 1 if args.strict else 0
    print("PASS: no release placeholders")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
