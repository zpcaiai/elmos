#!/usr/bin/env python3
"""Audit which Skill series in this repository are backed by executable code.

The question this answers is narrow and checkable: for each Skill series that
ships in the repository, is there (a) a runnable implementation, (b) a test
directory that exercises it, and (c) how many tests actually run?  A series with
Skill documents but no implementation is reported as ``spec-only`` - which is a
fact about the tree, not a judgement about the design.

    python3 -m scripts.modernization_b01_44.audit_repo [--json]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[2]

#: series label -> (skill/data globs, implementation dirs, test dir)
SERIES: dict[str, tuple[tuple[str, ...], tuple[str, ...], str | None]] = {
    "modernization-b01-44": (
        ("skills/modernization-skills-batch-01-44/batch_*/skills/*/SKILL.md",),
        ("scripts/modernization_b01_44",),
        "tests/modernization-b01-44",
    ),
    "precision-migration-b01-44": (
        ("skills/precision-migration-skills-batch-01-44/**/SKILL.md",),
        ("scripts/precision_migration",),
        "tests/precision-migration",
    ),
    "repository-migration-platform-b1-38": (
        ("skills/repository-migration-platform-skills-batch1-38/**/SKILL.md",),
        ("skills/repository-migration-platform-skills-batch1-38/scripts",),
        "skills/repository-migration-platform-skills-batch1-38/tests",
    ),
    "uir-java-python": (
        ("engines/uir-java-python/**/*.md",),
        ("engines/uir-java-python/j2p", "engines/uir-java-python/runtime"),
        "engines/uir-java-python/tests",
    ),
    "codex-skills-b1-55": (
        ("elmos-codex-skills-batch1-55-complete/**/SKILL.md",),
        (),
        None,
    ),
    "codex-skills-b40-55": (
        ("elmos-codex-skills-batch40-55-complete/**/SKILL.md",),
        (),
        None,
    ),
    "codex-skills-b66-80": (
        ("elmos-codex-skills-batch66-80-complete/**/SKILL.md",),
        ("scripts/test-suite-b66-80",),
        "tests/test-suite",
    ),
    "language-packs-b81-95": (
        ("elmos-language-packs-batch81-95-complete/**/SKILL.md",),
        (),
        None,
    ),
    "codex-skills-b97-104": (
        ("elmos-codex-skills-batch97-104-complete/**/SKILL.md",),
        (),
        None,
    ),
    "product-convergence-b46": (
        ("batch46-product-convergence-complete-skills/**/SKILL.md", ".agents/skills/conv-*/SKILL.md"),
        ("scripts/product-convergence",),
        "tests/product-convergence",
    ),
    "product-closure-b56": (
        ("elmos-codex-skills-batch56-product-closure/**/SKILL.md",
         "elmos-codex-skills-batch56a-product-closure/**/SKILL.md"),
        ("scripts/product-closure-batch56a", "scripts/product-closure-convergence"),
        "tests/product-closure-batch56",
    ),
    "project-synthesis-b46-65": (
        ("elmos-project-synthesis-batch46-60/**/*.md",
         "elmos-project-synthesis-batch61-65/**/*.md"),
        ("engines/project-synthesis-engine",),
        None,
    ),
    "runtime-agent-skills": (
        ("agent-skills/**/SKILL.md", ".agents/skills/**/SKILL.md"),
        ("modules", "engines", "apps", "contracts"),
        None,
    ),
}

JVM_EXTENSIONS = (".java", ".kt")
CODE_EXTENSIONS = (".py", ".ts", ".tsx", ".cs", ".java", ".kt", ".go", ".rs")


@dataclass
class SeriesReport:
    name: str
    skills: int
    implementation_dirs: list[str]
    implementation_files: int
    implementation_lines: int
    test_dir: str | None
    tests_ran: int | None
    verdict: str
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "series": self.name,
            "skills": self.skills,
            "implementation_dirs": self.implementation_dirs,
            "implementation_files": self.implementation_files,
            "implementation_lines": self.implementation_lines,
            "test_dir": self.test_dir,
            "tests_ran": self.tests_ran,
            "verdict": self.verdict,
            "notes": self.notes,
        }


def count_code(directory: Path) -> tuple[int, int]:
    files = 0
    lines = 0
    for path in directory.rglob("*"):
        if not path.is_file() or path.suffix not in CODE_EXTENSIONS:
            continue
        if "__pycache__" in path.parts or "/target/" in path.as_posix():
            continue
        files += 1
        try:
            lines += len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        except OSError:
            pass
    return files, lines


def run_tests(test_dir: Path) -> int | None:
    if not test_dir.is_dir():
        return None
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", str(test_dir), "-p", "test_*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PATH": "/usr/bin:/bin", "HOME": "/tmp"},
    )
    match = re.search(r"^Ran (\d+) tests?", proc.stderr, re.M)
    if not match:
        return None
    return int(match.group(1)) if proc.returncode == 0 else -int(match.group(1))


def audit(run_suites: bool = True) -> list[SeriesReport]:
    reports: list[SeriesReport] = []
    for name, (skill_globs, impl_dirs, test_dir) in SERIES.items():
        skills = 0
        for pattern in skill_globs:
            skills += len(list(ROOT.glob(pattern)))
        files = lines = 0
        present_dirs: list[str] = []
        for rel in impl_dirs:
            directory = ROOT / rel
            if not directory.is_dir():
                continue
            present_dirs.append(rel)
            f, l = count_code(directory)
            files += f
            lines += l
        tests_ran = run_tests(ROOT / test_dir) if (run_suites and test_dir) else None

        notes: list[str] = []
        if not present_dirs:
            verdict = "spec-only"
            notes.append("no implementation directory is associated with this series")
        elif tests_ran is None:
            verdict = "code-without-suite"
            notes.append("implementation exists but no python suite is wired to it")
        elif tests_ran < 0:
            verdict = "suite-red"
            notes.append(f"suite fails ({-tests_ran} tests ran)")
        else:
            verdict = "code-and-tests"
        reports.append(
            SeriesReport(
                name=name,
                skills=skills,
                implementation_dirs=present_dirs,
                implementation_files=files,
                implementation_lines=lines,
                test_dir=test_dir,
                tests_ran=tests_ran,
                verdict=verdict,
                notes=notes,
            )
        )
    return reports


def jvm_summary() -> dict[str, Any]:
    pom = ROOT / "pom.xml"
    modules = re.findall(r"<module>([^<]+)</module>", pom.read_text(encoding="utf-8")) if pom.is_file() else []
    java_files = [
        p
        for p in ROOT.rglob("*.java")
        if ".git" not in p.parts and "target" not in p.parts
    ]
    return {
        "maven_modules": len(modules),
        "java_files": len(java_files),
        "java_lines": sum(
            len(p.read_text(encoding="utf-8", errors="ignore").splitlines()) for p in java_files
        ),
        "note": "Building this requires Maven Central; verify with `mvn -T1C verify` on a host that can reach it.",
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-run", action="store_true", help="skip executing the suites")
    args = parser.parse_args(list(argv) if argv is not None else None)

    reports = audit(run_suites=not args.no_run)
    jvm = jvm_summary()

    if args.json:
        json.dump(
            {"series": [r.as_dict() for r in reports], "jvm": jvm},
            sys.stdout,
            indent=2,
            ensure_ascii=False,
        )
        print()
        return 0

    width = max(len(r.name) for r in reports)
    print(f"{'series':<{width}}  {'skills':>7} {'code files':>10} {'code lines':>10} {'tests':>7}  verdict")
    print("-" * (width + 52))
    for report in sorted(reports, key=lambda r: r.name):
        tests = "-" if report.tests_ran is None else str(report.tests_ran)
        print(
            f"{report.name:<{width}}  {report.skills:>7} {report.implementation_files:>10} "
            f"{report.implementation_lines:>10} {tests:>7}  {report.verdict}"
        )
    print()
    print(
        f"JVM: {jvm['maven_modules']} maven modules, {jvm['java_files']} java files, "
        f"{jvm['java_lines']} lines - {jvm['note']}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
