#!/usr/bin/env python3
"""Heuristic anti-pattern scanner. Informational only; never authoritative evidence."""

from __future__ import annotations
import argparse
import re
from pathlib import Path

PATTERNS = {
    "manual-pass-json": re.compile(r'["\'](?:passed|certified)["\']\s*:\s*true', re.I),
    "echo-pass": re.compile(r'\becho\s+["\']?(?:PASS|PASSED|CERTIFIED)\b', re.I),
    "generic-set-passed": re.compile(r'\bsetStatus\s*\(\s*PASSED\s*\)', re.I),
    "evidence-exists-pass": re.compile(r'evidence.*exists.*pass', re.I),
    "assert-true": re.compile(r'\bassert(?:True|_true)\s*\(\s*(?:true|True)\s*\)', re.I),
}
SKIP = {".git", "node_modules", "target", "build", ".idea", ".venv", "venv"}
TEXT_SUFFIXES = {".java", ".kt", ".py", ".go", ".rs", ".ts", ".js", ".sh", ".md", ".json", ".yaml", ".yml", ".rego"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("root", nargs="?", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    findings = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, pattern in PATTERNS.items():
            for m in pattern.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                findings.append((name, p, line, m.group(0)[:120]))
    for name, p, line, snippet in findings:
        print(f"WARN {name}: {p}:{line}: {snippet}")
    print(f"\nHeuristic findings: {len(findings)}")
    print("This scanner is informational only. Findings are not proof of fraud and a clean scan is not certification evidence.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
