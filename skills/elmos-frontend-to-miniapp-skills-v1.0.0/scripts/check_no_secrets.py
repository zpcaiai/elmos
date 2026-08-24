#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from common import package_root

PATTERNS = {
    "private-key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai-key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
    "aws-access-key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
}
TEXT_EXTENSIONS = {
    ".md", ".yaml", ".yml", ".json", ".py", ".sh", ".ps1", ".ts", ".tsx",
    ".js", ".jsx", ".vue", ".dart", ".txt", ".toml", ".xml", ".html", ".css"
}


def scan(root: Path) -> dict:
    findings: list[dict] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for kind, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append({
                    "kind": kind,
                    "path": path.relative_to(root).as_posix(),
                    "line": line,
                    "fingerprint": f"{kind}:{len(match.group(0))}",
                })
    return {"ok": not findings, "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = (args.root or package_root()).resolve()
    result = scan(root)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for finding in result["findings"]:
            print(f"ERROR: {finding['kind']} at {finding['path']}:{finding['line']}")
        print(f"secret_scan_ok={result['ok']} findings={len(result['findings'])}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
