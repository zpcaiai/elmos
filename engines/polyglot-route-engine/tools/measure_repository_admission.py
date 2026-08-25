#!/usr/bin/env python3
"""Repository conversion admission measurement -- all 13 engine languages.

Answers one question with numbers instead of adjectives: for a real repository,
what fraction of the source actually enters the bounded `typed-pure-function-v1`
conversion subset?

It drives the production instrument, `discovery.discover_unit`, so every verdict
carries the pinned-toolchain attestation.  That is why this script must run on
the pinned macOS toolchain host -- off it, `discover_unit` returns
`EXACT_TOOLCHAIN_PLATFORM_MISMATCH` and every unit is `NOT_RUN`.

Run it the way the repository runs its other engine tools (never
`uv run --locked python tools/...` from the repository root -- `--locked` only
applies inside the engine's own project and `uv` silently falls back to the
PATH python, which cannot find this file):

    uv --directory engines/polyglot-route-engine run --locked python \
        tools/measure_repository_admission.py \
        --repository ~/DevProjects/AIProjects/langgraph \
        --language python \
        --output .ai/admission-<name>-python.json

Closed vocabulary, same discipline as tools/capability_probe.py:

    READY        the unit entered the bounded subset
    UNSUPPORTED  the engine rejected it -- a real boundary
    NOT_RUN      the engine could not decide here (toolchain, analyzer) --
                 this is NOT a boundary and is never folded into UNSUPPORTED
    UNREADABLE / NO_CANDIDATE_DECLARATION

READY counts admission, not correctness.  A unit that enters the subset still
has to survive route execution, target build and behavior comparison before
anything may be said about accuracy.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from elmos_polyglot_route.discovery import Verdict, discover_unit
from elmos_polyglot_route.models import SUPPORTED_LANGUAGES, Language
from elmos_polyglot_route.react_repository import react_project_descriptor

EXTENSIONS: dict[Language, tuple[str, ...]] = {
    "python": (".py",),
    "java": (".java",),
    "typescript": (".ts",),
    "react": (".tsx", ".ts"),
    "go": (".go",),
    "rust": (".rs",),
    "csharp": (".cs",),
    "cpp": (".cpp", ".cc", ".cxx"),
    "objc": (".m",),
    "swift": (".swift",),
    "kotlin": (".kt",),
    "php": (".php",),
    "flutter": (".dart",),
}
if set(EXTENSIONS) != set(SUPPORTED_LANGUAGES):
    raise RuntimeError("ADMISSION_MEASUREMENT_LANGUAGE_CATALOG_DRIFT")

SKIP_DIR_PARTS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "build", "dist",
    "target", "vendor", ".idea", "site-packages", ".eggs", "Pods",
    ".gradle", ".dart_tool", "obj", "bin", ".build", "DerivedData",
}


def repository_commit(root: Path) -> str | None:
    """Read HEAD without letting git touch the index (no lock files)."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
            env={"GIT_OPTIONAL_LOCKS": "0", "PATH": "/usr/bin:/bin:/usr/local/bin"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None


def iter_sources(root: Path, language: Language) -> list[Path]:
    suffixes = EXTENSIONS[language]
    found: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix not in suffixes:
            continue
        if SKIP_DIR_PARTS & set(path.relative_to(root).parts[:-1]):
            continue
        found.append(path)
    return found


def is_test_path(relative: str, language: Language) -> bool:
    parts = relative.split("/")
    name = parts[-1].lower()
    directories = {part.lower() for part in parts[:-1]}
    if directories & {"test", "tests", "testing", "spec", "specs", "__tests__"}:
        return True
    return (
        name.startswith("test_")
        or name.endswith("_test" + Path(relative).suffix)
        or name.endswith(".test" + Path(relative).suffix)
        or name.endswith(".spec" + Path(relative).suffix)
        or (language == "java" and name.endswith("test.java"))
        or (language == "csharp" and name.endswith("tests.cs"))
    )


def measure(
    root: Path,
    language: Language,
    *,
    include_tests: bool,
    limit: int | None,
) -> dict[str, Any]:
    files = iter_sources(root, language)
    react_descriptor: dict[str, Any] | None = None
    if language == "react":
        try:
            react_descriptor = react_project_descriptor(root)
        except Exception as error:
            return {
                "measurement_status": "NOT_RUN",
                "measurement_scope": "react-exact-project-context",
                "counts": {
                    "source_files_found": len(files),
                    "source_files_measured": 0,
                    "test_files_excluded": 0,
                    "source_bytes_measured": 0,
                    "coverage_subjects": 0,
                    "candidate_declarations": 0,
                    "ready_units": 0,
                    "unsupported_units": 0,
                    "not_run_units": len(files),
                    "instrument_errors": 1,
                },
                "rates": {
                    "ready_over_coverage_subjects": None,
                    "ready_over_decided_units": None,
                    "not_run_share": 1.0 if files else None,
                },
                "verdicts": {Verdict.NOT_RUN: len(files)} if files else {},
                "blocker_codes": {"REACT_PROJECT_DESCRIPTOR_NOT_READY": len(files)}
                if files
                else {},
                "ready_units": [],
                "instrument_errors": [
                    {
                        "path": ".",
                        "error": f"{type(error).__name__}:{error}"[:240],
                    }
                ],
            }
    verdicts: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    ready: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    subjects_total = 0
    candidates_total = 0
    measured = 0
    excluded = 0
    measured_bytes = 0

    for path in files:
        relative = path.relative_to(root).as_posix()
        if not include_tests and is_test_path(relative, language):
            excluded += 1
            continue
        if limit is not None and measured >= limit:
            break
        measured += 1
        try:
            measured_bytes += path.stat().st_size
            unit: dict[str, Any] = {"id": relative, "source_path": relative}
            if react_descriptor is not None:
                unit["react_project_descriptor"] = react_descriptor
            result = discover_unit(root, unit, language)
        except Exception as error:  # RouteError / OSError -- an instrument failure, not a boundary
            errors.append({"path": relative, "error": f"{type(error).__name__}:{error}"[:240]})
            verdicts["INSTRUMENT_ERROR"] += 1
            continue

        subjects = result.get("coverage_subjects")
        if isinstance(subjects, list):
            subjects_total += len(subjects)
            candidates_total += sum(1 for item in subjects if isinstance(item, dict) and item.get("candidate"))
        else:
            count = result.get("coverage_subject_count")
            if isinstance(count, int):
                subjects_total += count
            declared = result.get("candidates")
            if isinstance(declared, list):
                candidates_total += len(declared)

        eligible = result.get("eligible_candidates")
        if isinstance(eligible, list):
            for item in eligible:
                ready.append({"path": relative, "candidate": item.get("candidate") or item.get("function_name")})
            verdicts[Verdict.READY] += len(eligible)

        for group in ("rejected_candidates", "coverage_blockers"):
            items = result.get(group)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                blockers[str(item.get("blocker_code", "UNKNOWN"))] += 1
                verdicts[str(item.get("verdict", Verdict.UNSUPPORTED))] += 1

        if result.get("verdict") in {Verdict.UNREADABLE, Verdict.NO_CANDIDATE_DECLARATION}:
            verdicts[str(result["verdict"])] += 1

    decided = verdicts[Verdict.READY] + verdicts[Verdict.UNSUPPORTED]
    return {
        "measurement_status": "LOCAL_MEASURED",
        "measurement_scope": (
            "react-exact-project-context"
            if language == "react"
            else "flutter-import-free-pure-dart"
            if language == "flutter"
            else "typed-pure-function-v1"
        ),
        "counts": {
            "source_files_found": len(files),
            "source_files_measured": measured,
            "test_files_excluded": excluded,
            "source_bytes_measured": measured_bytes,
            "coverage_subjects": subjects_total,
            "candidate_declarations": candidates_total,
            "ready_units": verdicts[Verdict.READY],
            "unsupported_units": verdicts[Verdict.UNSUPPORTED],
            "not_run_units": verdicts[Verdict.NOT_RUN],
            "instrument_errors": len(errors),
        },
        "rates": {
            "ready_over_coverage_subjects": (
                verdicts[Verdict.READY] / subjects_total if subjects_total else None
            ),
            "ready_over_decided_units": (verdicts[Verdict.READY] / decided if decided else None),
            "not_run_share": (
                verdicts[Verdict.NOT_RUN] / sum(verdicts.values()) if sum(verdicts.values()) else None
            ),
        },
        "verdicts": dict(verdicts.most_common()),
        "blocker_codes": dict(blockers.most_common(50)),
        "ready_units": ready[:200],
        "instrument_errors": errors[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path, action="append",
                        help="repository root; repeat for several")
    parser.add_argument("--language", required=True, choices=SUPPORTED_LANGUAGES)
    parser.add_argument("--include-tests", action="store_true")
    parser.add_argument("--limit-files", type=int, default=None,
                        help="cap files per repository; the cap is recorded in the report")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    repositories = []
    for raw in arguments.repository:
        root = raw.expanduser().resolve(strict=True)
        print(f"[measure] {root}", file=sys.stderr, flush=True)
        record = measure(
            root,
            arguments.language,
            include_tests=arguments.include_tests,
            limit=arguments.limit_files,
        )
        record["repository"] = root.name
        record["repository_path"] = str(root)
        record["commit"] = repository_commit(root)
        repositories.append(record)

    totals: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    for record in repositories:
        totals.update(record["counts"])
        blockers.update(record["blocker_codes"])
        verdicts.update(record["verdicts"])

    decided = verdicts[Verdict.READY] + verdicts[Verdict.UNSUPPORTED]
    report = {
        "kind": "elmos.repository-conversion-admission-measurement",
        "schema_version": "1.0.0",
        "profile": "typed-pure-function-v1",
        "instrument": "elmos_polyglot_route.discovery.discover_unit",
        "source_language": arguments.language,
        "include_tests": arguments.include_tests,
        "file_limit_per_repository": arguments.limit_files,
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "aggregate": {
            "repositories": len(repositories),
            "counts": dict(totals),
            "rates": {
                "ready_over_coverage_subjects": (
                    totals["ready_units"] / totals["coverage_subjects"]
                    if totals["coverage_subjects"] else None
                ),
                "ready_over_decided_units": (verdicts[Verdict.READY] / decided if decided else None),
            },
            "verdicts": dict(verdicts.most_common()),
            "blocker_codes": dict(blockers.most_common(50)),
        },
        "repositories": repositories,
        "execution_status": "LOCAL_EXECUTED",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
        "limitations": [
            "Admission measurement only: no conversion, target build or behavior comparison was run.",
            "READY means the unit entered the bounded subset, not that its conversion is correct.",
            "NOT_RUN verdicts are recorded separately and never counted as boundaries; a high "
            "not_run_share means the measurement did not decide, not that the engine refused.",
            "A zero READY count on this corpus does not prove that no authorized corpus contains "
            "a positive example.",
        ],
    }

    text = json.dumps(report, indent=2)
    if arguments.output:
        arguments.output.expanduser().write_text(text, encoding="utf-8")
        print(f"wrote {arguments.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
