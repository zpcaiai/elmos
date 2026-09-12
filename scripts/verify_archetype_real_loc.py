#!/usr/bin/env python3
"""
verify_archetype_real_loc.py

Strict Physical & Effective LOC Auditor for Enterprise Reference Projects (Path A).
Audits files across Go, TypeScript, Java, C#, and Rust projects under:
engines/project-synthesis-engine/enterprise_reference_projects/

Calculates:
- Physical Lines (wc -l)
- Effective Code Lines (excluding pure blank lines & comments)
- Comment Lines & Blank Lines
- Per-project and Per-language totals
- Verification against >= 40,000 LOC target.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


LANGUAGE_EXTENSIONS = {
    ".go": "Go",
    ".ts": "TypeScript",
    ".java": "Java",
    ".cs": "C#",
    ".rs": "Rust",
}

COMMENT_PREFIXES = {
    ".go": ("//", "/*", "*"),
    ".ts": ("//", "/*", "*"),
    ".java": ("//", "/*", "*"),
    ".cs": ("//", "/*", "*"),
    ".rs": ("//", "/*", "*"),
}


def analyze_file(filepath: Path) -> Dict[str, int]:
    ext = filepath.suffix.lower()
    if ext not in LANGUAGE_EXTENSIONS:
        return {"total": 0, "code": 0, "comment": 0, "blank": 0}

    total_lines = 0
    code_lines = 0
    comment_lines = 0
    blank_lines = 0

    in_multiline_comment = False
    prefixes = COMMENT_PREFIXES.get(ext, ("//", "/*", "*"))

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                total_lines += 1
                stripped = line.strip()

                if not stripped:
                    blank_lines += 1
                    continue

                if in_multiline_comment:
                    comment_lines += 1
                    if "*/" in stripped:
                        in_multiline_comment = False
                    continue

                if stripped.startswith("/*"):
                    comment_lines += 1
                    if "*/" not in stripped:
                        in_multiline_comment = True
                    continue

                if any(stripped.startswith(p) for p in prefixes if p != "/*"):
                    comment_lines += 1
                    continue

                code_lines += 1
    except Exception as e:
        print(f"Warning reading {filepath}: {e}", file=sys.stderr)

    return {
        "total": total_lines,
        "code": code_lines,
        "comment": comment_lines,
        "blank": blank_lines,
    }


def audit_enterprise_projects(base_dir: Path) -> Dict[str, Any]:
    if not base_dir.exists():
        return {
            "error": f"Directory not found: {base_dir}",
            "projects": {},
            "languages": {},
            "total_physical_loc": 0,
            "total_effective_loc": 0,
            "total_files": 0,
            "target_met": False,
        }

    projects: Dict[str, Dict[str, Any]] = {}
    languages: Dict[str, Dict[str, int]] = {
        lang: {"total": 0, "code": 0, "comment": 0, "blank": 0, "files": 0}
        for lang in LANGUAGE_EXTENSIONS.values()
    }

    grand_total = {"total": 0, "code": 0, "comment": 0, "blank": 0, "files": 0}

    project_dirs = [d for d in base_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]
    project_dirs.sort(key=lambda d: d.name)

    for pdir in project_dirs:
        pname = pdir.name
        proj_stats = {
            "total": 0,
            "code": 0,
            "comment": 0,
            "blank": 0,
            "files": 0,
            "file_details": [],
        }

        EXCLUDE_DIRS = {"dist", "build", "target", "bin", "obj", "node_modules", ".git", ".idea", ".vscode"}
        for root, dirs, files in os.walk(pdir):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                fpath = Path(root) / fname
                ext = fpath.suffix.lower()
                if ext in LANGUAGE_EXTENSIONS:
                    res = analyze_file(fpath)
                    lang = LANGUAGE_EXTENSIONS[ext]

                    proj_stats["total"] += res["total"]
                    proj_stats["code"] += res["code"]
                    proj_stats["comment"] += res["comment"]
                    proj_stats["blank"] += res["blank"]
                    proj_stats["files"] += 1

                    languages[lang]["total"] += res["total"]
                    languages[lang]["code"] += res["code"]
                    languages[lang]["comment"] += res["comment"]
                    languages[lang]["blank"] += res["blank"]
                    languages[lang]["files"] += 1

                    grand_total["total"] += res["total"]
                    grand_total["code"] += res["code"]
                    grand_total["comment"] += res["comment"]
                    grand_total["blank"] += res["blank"]
                    grand_total["files"] += 1

                    rel_path = str(fpath.relative_to(pdir))
                    proj_stats["file_details"].append({
                        "path": rel_path,
                        "language": lang,
                        "lines": res["total"],
                        "code": res["code"],
                    })

        projects[pname] = proj_stats

    target_loc = 40000
    target_met = grand_total["total"] >= target_loc

    return {
        "base_directory": str(base_dir),
        "target_loc": target_loc,
        "total_physical_loc": grand_total["total"],
        "total_effective_loc": grand_total["code"],
        "total_comment_lines": grand_total["comment"],
        "total_blank_lines": grand_total["blank"],
        "total_files": grand_total["files"],
        "target_met": target_met,
        "projects": projects,
        "languages": languages,
    }


def print_report(audit_data: Dict[str, Any], detailed: bool = False) -> None:
    print("=" * 80)
    print("      ENTERPRISE REFERENCE PROJECTS (PATH A) LOC AUDIT REPORT")
    print("=" * 80)
    print(f"Base Directory:     {audit_data.get('base_directory', 'N/A')}")
    print(f"Target LOC:         {audit_data.get('target_loc', 40000):,}")
    print(f"Total Physical LOC: {audit_data.get('total_physical_loc', 0):,}")
    print(f"Total Effective Code: {audit_data.get('total_effective_loc', 0):,}")
    print(f"Total Comment Lines:{audit_data.get('total_comment_lines', 0):,}")
    print(f"Total Blank Lines:  {audit_data.get('total_blank_lines', 0):,}")
    print(f"Total Source Files: {audit_data.get('total_files', 0):,}")
    print(f"Target Met (>=40k): {'PASSED' if audit_data.get('target_met') else 'PENDING / IN-PROGRESS'}")
    print("-" * 80)

    print("\n[Per-Language Breakdown]")
    print(f"{'Language':<15} {'Files':<8} {'Physical LOC':<15} {'Effective Code':<15} {'Comments':<10}")
    print("-" * 65)
    for lang, s in sorted(audit_data.get("languages", {}).items()):
        print(f"{lang:<15} {s['files']:<8} {s['total']:<15,d} {s['code']:<15,d} {s['comment']:<10,d}")

    print("\n[Per-Project Breakdown]")
    print(f"{'Project Name':<32} {'Files':<8} {'Physical LOC':<15} {'Effective Code':<15}")
    print("-" * 72)
    for pname, ps in sorted(audit_data.get("projects", {}).items()):
        print(f"{pname:<32} {ps['files']:<8} {ps['total']:<15,d} {ps['code']:<15,d}")

    if detailed:
        print("\n[Top Source Files by Size]")
        all_files = []
        for pname, ps in audit_data.get("projects", {}).items():
            for f in ps.get("file_details", []):
                all_files.append((f"{pname}/{f['path']}", f["lines"], f["code"], f["language"]))
        all_files.sort(key=lambda x: x[1], reverse=True)
        for path, lines, code, lang in all_files[:30]:
            print(f"  {lines:5d} lines ({code:5d} code) [{lang:10}] {path}")
    print("=" * 80)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit LOC of enterprise reference projects")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("engines/project-synthesis-engine/enterprise_reference_projects"),
        help="Base directory of reference projects",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--detailed", action="store_true", help="Show top files")
    parser.add_argument("--fail-under", type=int, default=0, help="Exit with 1 if total LOC < value")

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    base_dir = args.dir
    if not base_dir.is_absolute():
        base_dir = repo_root / base_dir

    data = audit_enterprise_projects(base_dir)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_report(data, detailed=args.detailed)

    if args.fail_under > 0 and data["total_physical_loc"] < args.fail_under:
        print(f"\nAudit failed: total physical LOC {data['total_physical_loc']:,} < threshold {args.fail_under:,}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
