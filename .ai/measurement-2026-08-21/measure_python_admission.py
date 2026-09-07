"""ELMOS repository-conversion admission measurement (Python source).

Measures, for real repositories, what fraction of the source actually enters
the bounded `typed-pure-function-v1` conversion subset, using the engine's own
instruments rather than a reimplementation:

  layer 1  elmos_polyglot_route.project_graph.python_coverage_subjects
           -> the whole-repository coverage inventory: every declaration and
              module-body effect the engine says a COMPLETE conversion must
              cover, with its `candidate` flag and structural blockers.

  layer 2  elmos_polyglot_route.python_analyzer.analyze_python
           -> the semantic subset check, for candidates only. READY or a
              closed rejection code.

Deliberate scope limits, stated so they are not read away:

* `discovery.discover_unit` (the production entry) refuses to run off the
  pinned Darwin/arm64 toolchain with
  `EXACT_TOOLCHAIN_PLATFORM_MISMATCH:python:expected=Darwin/arm64`.  This
  script therefore calls the two toolchain-free layers underneath it directly.
  The analyzer *logic* is identical; the pinned-toolchain attestation is
  NOT_RUN.  These are analyzer-logic verdicts, not certified route evidence.
* READY means a unit entered the subset. It does NOT mean its conversion is
  correct. Correctness is the route-execution path and is measured separately.
* A file that cannot be parsed is reported as UNPARSEABLE, never as a boundary.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from elmos_polyglot_route.models import RouteError
from elmos_polyglot_route.project_graph import python_coverage_subjects
from elmos_polyglot_route.python_analyzer import analyze_python

SKIP_DIR_PARTS = {
    ".git", ".hg", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "build", "dist", "target",
    "vendor", ".idea", "site-packages", ".eggs",
}


def iter_python_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        if not path.is_file() or path.is_symlink():
            continue
        if SKIP_DIR_PARTS & set(path.relative_to(root).parts[:-1]):
            continue
        out.append(path)
    return out


def is_test_file(relative: str) -> bool:
    parts = relative.split("/")
    name = parts[-1]
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts[:-1]
        or "test" in parts[:-1]
        or "testing" in parts[:-1]
    )


def measure_repository(root: Path, *, include_tests: bool) -> dict:
    files = iter_python_files(root)

    declaration_kinds: Counter[str] = Counter()
    subject_kinds: Counter[str] = Counter()
    structural_blockers: Counter[str] = Counter()
    semantic_rejections: Counter[str] = Counter()

    ready: list[dict] = []
    unparseable: list[dict] = []

    files_measured = 0
    files_skipped_tests = 0
    total_bytes = 0
    total_subjects = 0
    total_candidates = 0
    clean_candidates = 0  # candidate with no structural blocker -> reaches layer 2

    for path in files:
        relative = path.relative_to(root).as_posix()
        if not include_tests and is_test_file(relative):
            files_skipped_tests += 1
            continue
        files_measured += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as error:
            unparseable.append({"path": relative, "error": type(error).__name__})
            continue
        total_bytes += len(source.encode("utf-8"))
        try:
            tree = ast.parse(source, filename=path.name)
        except (SyntaxError, ValueError, RecursionError) as error:
            unparseable.append({"path": relative, "error": type(error).__name__})
            continue

        subjects = python_coverage_subjects(tree, relative)
        total_subjects += len(subjects)
        for subject in subjects:
            subject_kinds[subject.subject_kind] += 1
            declaration_kinds[subject.declaration_kind] += 1
            if not subject.candidate:
                for code in subject.blocking_reasons:
                    structural_blockers[code] += 1
                continue
            total_candidates += 1
            if subject.blocking_reasons:
                for code in subject.blocking_reasons:
                    structural_blockers[code] += 1
                continue
            clean_candidates += 1
            try:
                analyze_python(path, subject.name)
            except RouteError as error:
                semantic_rejections[str(error).split(":", 1)[0]] += 1
            except RecursionError:
                semantic_rejections["ANALYZER_RECURSION_LIMIT"] += 1
            else:
                ready.append({"path": relative, "function": subject.name})

    return {
        "counts": {
            "python_files_found": len(files),
            "python_files_measured": files_measured,
            "test_files_excluded": files_skipped_tests,
            "source_bytes_measured": total_bytes,
            "coverage_subjects": total_subjects,
            "candidate_subjects": total_candidates,
            "candidates_reaching_semantic_check": clean_candidates,
            "ready_units": len(ready),
            "unparseable_files": len(unparseable),
        },
        "rates": {
            "ready_over_coverage_subjects": (
                len(ready) / total_subjects if total_subjects else None
            ),
            "ready_over_candidate_subjects": (
                len(ready) / total_candidates if total_candidates else None
            ),
            "ready_over_semantic_checked": (
                len(ready) / clean_candidates if clean_candidates else None
            ),
        },
        "subject_kinds": dict(subject_kinds.most_common()),
        "declaration_kinds": dict(declaration_kinds.most_common()),
        "structural_blockers": dict(structural_blockers.most_common()),
        "semantic_rejections": dict(semantic_rejections.most_common()),
        "ready_units": ready[:200],
        "unparseable": unparseable[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo", action="append", default=None)
    arguments = parser.parse_args()

    corpus_root: Path = arguments.corpus_root.resolve(strict=True)
    names = arguments.repo or sorted(
        entry.name for entry in corpus_root.iterdir() if entry.is_dir() and not entry.is_symlink()
    )

    repositories = []
    for name in names:
        root = (corpus_root / name).resolve(strict=True)
        print(f"[measure] {name}", file=sys.stderr, flush=True)
        record = measure_repository(root, include_tests=arguments.include_tests)
        record["repository"] = name
        repositories.append(record)

    totals: Counter[str] = Counter()
    structural: Counter[str] = Counter()
    semantic: Counter[str] = Counter()
    for record in repositories:
        totals.update(record["counts"])
        structural.update(record["structural_blockers"])
        semantic.update(record["semantic_rejections"])

    report = {
        "kind": "elmos.repository-conversion-admission-measurement",
        "schema_version": "1.0.0",
        "profile": "typed-pure-function-v1",
        "source_language": "python",
        "instruments": {
            "coverage_inventory": "elmos_polyglot_route.project_graph.python_coverage_subjects",
            "semantic_subset_check": "elmos_polyglot_route.python_analyzer.analyze_python",
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
        },
        "toolchain_attestation": {
            "status": "NOT_RUN",
            "reason": (
                "discovery.discover_unit refuses off the pinned toolchain with "
                "EXACT_TOOLCHAIN_PLATFORM_MISMATCH:python:expected=Darwin/arm64. "
                "The two layers underneath were called directly; analyzer logic is "
                "identical, the attestation is not."
            ),
        },
        "include_tests": arguments.include_tests,
        "aggregate": {
            "repositories": len(repositories),
            "counts": dict(totals),
            "rates": {
                "ready_over_coverage_subjects": (
                    totals["ready_units"] / totals["coverage_subjects"]
                    if totals["coverage_subjects"] else None
                ),
                "ready_over_candidate_subjects": (
                    totals["ready_units"] / totals["candidate_subjects"]
                    if totals["candidate_subjects"] else None
                ),
                "ready_over_semantic_checked": (
                    totals["ready_units"] / totals["candidates_reaching_semantic_check"]
                    if totals["candidates_reaching_semantic_check"] else None
                ),
            },
            "structural_blockers": dict(structural.most_common(40)),
            "semantic_rejections": dict(semantic.most_common(40)),
        },
        "repositories": repositories,
        "limitations": [
            "Admission measurement only: no conversion, no target build, no behavior comparison was run.",
            "READY means the unit entered the bounded subset, not that its conversion is correct.",
            "Pinned-toolchain attestation is NOT_RUN; this is analyzer-logic evidence, not certified route evidence.",
            "A zero READY count does not prove no authorized corpus contains a positive example.",
        ],
    }

    text = json.dumps(report, indent=2)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
        print(
            f"wrote {arguments.output} sha256={hashlib.sha256(text.encode('utf-8')).hexdigest()}",
            file=sys.stderr,
        )
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
