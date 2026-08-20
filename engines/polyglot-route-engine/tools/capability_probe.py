#!/usr/bin/env python3
"""Answer "what does this engine actually do right now" by running it.

WHY THIS EXISTS

The engine already refuses to treat a file's presence as evidence that a route
works (`filePresenceIsEvidence: false`). It applies no such rule to claims
about *itself*. Every capability question -- can Kotlin be a target, does the
pipeline handle multi-function files, is PHP enumerable -- has been answered by
reading code, and reading code has a specific failure mode that produced three
wrong answers in one afternoon:

    A rejection code in an intermediate layer is not the system's boundary.

`discover_unit()` returns MULTIPLE_ELIGIBLE_FUNCTIONS_REQUIRE_EXPLICIT_PARTITION
for a multi-function file, which reads as "unsupported". `discover_repository()`
then splits that same result into one READY unit per function. Both are true;
only the second is the boundary. Nothing short of running it tells you which
layer you are looking at.

So this probe never infers. For each capability it calls the real entry point
and records what came back.

THE DISTINCTION THAT MATTERS MOST

`analyze()` validates the pinned toolchain before it dispatches, so a machine
without Apple clang 21 or Swift 6.3.3 gets `EXACT_TOOLCHAIN_UNAVAILABLE` -- and
that says nothing whatsoever about whether the capability exists. Collapsing
"cannot be probed here" into "not supported" is the same mistake as collapsing
an intermediate rejection into a boundary, and it is why the verdict vocabulary
below keeps them apart:

    SUPPORTED      ran, succeeded
    REJECTED:code  ran, refused -- a real boundary
    NOT_PROBED     could not run here -- NOT a capability claim
    ERROR:code     unexpected; treat as a probe defect until explained

A `NOT_PROBED` row is an instruction to re-run on the Mac, never an answer.

USAGE

From the repository root -- `--locked` only has effect inside the engine's own
project, so the `--directory` form is the one that works from anywhere:

    make capability-probe
    make capability-probe-json

    uv --directory engines/polyglot-route-engine run --locked \
        python tools/capability_probe.py

Running `uv run ...` from the repository root silently falls back to whatever
`python3` is on PATH and then cannot find this file at all.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from elmos_polyglot_route.models import (  # noqa: E402
    COMPLETE_MATRIX_LANGUAGES,
    DEPRECATED_LANGUAGES,
    PENDING_ANALYZER_LANGUAGES,
    Language,
    RouteError,
)

SCHEMA_VERSION = "1.0.0"
KIND = "elmos.capability-probe"

#: A toolchain that is absent on this machine says nothing about the engine.
_NOT_PROBED_PREFIXES = ("EXACT_TOOLCHAIN_", "MODULE_INVENTORY_SOURCE_CHANGED")

#: ...with one exception. `UNREGISTERED` means the language has no pinned
#: toolchain entry at all, which is a property of the engine, not of the
#: machine asking: it cannot be a source anywhere, so it is a real boundary and
#: must not hide inside the "re-run elsewhere" bucket.
_MACHINE_INDEPENDENT_TOOLCHAIN_CODES = frozenset({"EXACT_TOOLCHAIN_UNREGISTERED"})

#: Refusals that are a routing decision rather than a boundary. Python is
#: enumerated through CPython's `ast` in `discovery`, so `inventory_module`
#: declining it is the design working, not a gap -- and reporting it as
#: REJECTED would recreate the exact confusion this probe exists to end.
_BY_DESIGN_CODES = frozenset({"PYTHON_MODULE_INVENTORY_USES_CPYTHON_AST"})


def _verdict(run: Callable[[], Any]) -> str:
    try:
        run()
    except RouteError as error:
        code = str(error)
        head = code.split(":")[0]
        if head in _MACHINE_INDEPENDENT_TOOLCHAIN_CODES:
            return f"REJECTED:{head}"
        if code.startswith(_NOT_PROBED_PREFIXES):
            return f"NOT_PROBED:{head}"
        if head in _BY_DESIGN_CODES:
            return f"BY_DESIGN:{head}"
        return f"REJECTED:{head}"
    except FileNotFoundError:
        return "NOT_PROBED:BINARY_ABSENT"
    except Exception as error:  # noqa: BLE001 - a probe defect must be visible, not swallowed
        return f"ERROR:{type(error).__name__}"
    return "SUPPORTED"


# --- fixtures ---------------------------------------------------------------

#: One `clamp`-shaped function per language: the canonical `typed-pure-function-v1`
#: shape, deliberately identical in behaviour so a rejection is about the
#: language surface and never about what the function does.
_SOURCE_FIXTURES: dict[str, tuple[str, str]] = {
    "java": ("Subject.java", "public final class Subject {\n  public static long clamp(long v) { return v; }\n}\n"),
    "python": ("subject.py", "def clamp(v: int) -> int:\n    return v\n"),
    "csharp": ("Subject.cs", "public static class Subject {\n  public static long clamp(long v) { return v; }\n}\n"),
    "typescript": ("subject.ts", "export function clamp(v: number): number {\n  return v;\n}\n"),
    "go": ("subject.go", "package subject\n\nfunc clamp(v int64) int64 {\n\treturn v\n}\n"),
    "rust": ("subject.rs", "pub fn clamp(v: i64) -> i64 {\n    return v;\n}\n"),
    "cpp": ("subject.cpp", "#include <cstdint>\nstd::int64_t clamp(std::int64_t v) { return v; }\n"),
    "objc": ("subject.m", "long long clamp(long long v) { return v; }\n"),
    "swift": ("subject.swift", "func clamp(_ v: Int64) -> Int64 {\n    return v\n}\n"),
    "php": ("subject.php", "<?php\n\ndeclare(strict_types=1);\n\nfunction clamp(int $v): int\n{\n    return $v;\n}\n"),
    # The three languages with no analyzer still get a fixture. Reporting
    # NO_FIXTURE for them made "nobody wrote a fixture" and "there is no
    # frontend" the same cell, which is the ambiguity this probe exists to
    # remove: every cell has to be something the engine actually said.
    "kotlin": ("subject.kt", "fun clamp(v: Long): Long {\n    return v\n}\n"),
    "react": ("subject.tsx", "export function clamp(v: number): number {\n  return v;\n}\n"),
    "flutter": ("subject.dart", "int clamp(int v) {\n  return v;\n}\n"),
}

#: Constructs the IR has no representation for. Probed through CPython's ast
#: directly rather than `analyze()`, because the boundary is the IR's -- the
#: whitelist is `name / literal / binary / return / if` for every language --
#: and going through `analyze()` would need a pinned interpreter to say so.
_CONSTRUCT_FIXTURES: dict[str, str] = {
    "call": "def probe(v: int) -> int:\n    return helper(v)\n",
    "assignment": "def probe(v: int) -> int:\n    x = v\n    return x\n",
    "exception": "def probe(v: int) -> int:\n    try:\n        return v\n    except ValueError:\n        return 0\n",
    "loop": "def probe(v: int) -> int:\n    while v > 0:\n        v = v - 1\n    return v\n",
    # A class *beside* the function is a file-closure question, not an IR one:
    # enumeration records it as an obligation and the function still lifts. Kept
    # separate from the IR probe below because the first run of this probe
    # labelled it "class" and reported SUPPORTED, which read as "objects work".
    "class_declared_beside_function": "class Holder:\n    pass\n\ndef probe(v: int) -> int:\n    return v\n",
    # The IR question: can a value be reached through anything but a name?
    "attribute_access": "def probe(v: int) -> int:\n    return v.numerator\n",
    "subscript": "def probe(v: int) -> int:\n    return v[0]\n",
    "async": "async def probe(v: int) -> int:\n    return v\n",
}


def _canonical_ir() -> Any:
    from elmos_polyglot_route.native import SemanticIR

    return SemanticIR.from_mapping(
        {
            "schema_version": "1.0.0",
            "source_language": "java",
            "source_file": "Subject.java",
            "analyzer": "capability-probe",
            "analyzer_version": "0",
            "diagnostics": [],
            "functions": [
                {
                    "name": "clamp",
                    "return_type": "integer",
                    "parameters": [{"name": "v", "type": "integer"}],
                    "body": [{"kind": "return", "expression": {"kind": "name", "value": "v"}}],
                }
            ],
        }
    )


# --- probes -----------------------------------------------------------------


def probe_emission() -> dict[str, str]:
    """Can each declared language be an emission target? Pure Python, always conclusive."""
    from elmos_polyglot_route.emitter import emit

    ir = _canonical_ir()
    return {language: _verdict(lambda language=language: emit(ir, language)) for language in COMPLETE_MATRIX_LANGUAGES}


def probe_lifting(directory: Path) -> dict[str, str]:
    """Can each declared language be a source? Needs that language's pinned toolchain."""
    from elmos_polyglot_route.native import analyze

    results: dict[str, str] = {}
    for language in COMPLETE_MATRIX_LANGUAGES:
        fixture = _SOURCE_FIXTURES.get(language)
        if fixture is None:
            results[language] = "NOT_PROBED:NO_FIXTURE"
            continue
        name, body = fixture
        path = directory / f"lift-{language}-{name}"
        path.write_text(body, encoding="utf-8")
        results[language] = _verdict(lambda p=path, l=language: analyze(p, l, "clamp"))
    return results


def probe_module_enumeration(directory: Path) -> dict[str, str]:
    """Can each language's whole file be enumerated? This is what file closure rests on."""
    from elmos_polyglot_route.native import inventory_module

    results: dict[str, str] = {}
    for language in COMPLETE_MATRIX_LANGUAGES:
        fixture = _SOURCE_FIXTURES.get(language)
        if fixture is None:
            results[language] = "NOT_PROBED:NO_FIXTURE"
            continue
        name, body = fixture
        path = directory / f"inv-{language}-{name}"
        path.write_text(body, encoding="utf-8")
        results[language] = _verdict(lambda p=path, l=language: inventory_module(p, l))
    return results


def probe_subset_boundary(directory: Path) -> dict[str, str]:
    """Which constructs does the IR have no representation for, and what is the exact code?

    Answers the question the backlog kept getting wrong by inference. A
    `REJECTED:` row here is a structural boundary, not a policy choice: the IR
    whitelist has no node to hold the construct at all.
    """
    from elmos_polyglot_route.python_analyzer import analyze_python

    results: dict[str, str] = {}
    for construct, body in _CONSTRUCT_FIXTURES.items():
        path = directory / f"construct-{construct}.py"
        path.write_text(body, encoding="utf-8")
        results[construct] = _verdict(lambda p=path: analyze_python(p, "probe"))
    return results


def run() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="elmos-capability-probe-") as temporary:
        directory = Path(temporary)
        report = {
            "schema_version": SCHEMA_VERSION,
            "kind": KIND,
            "declared_languages": list(COMPLETE_MATRIX_LANGUAGES),
            "declared_pending_analyzer": list(PENDING_ANALYZER_LANGUAGES),
            "declared_deprecated": list(DEPRECATED_LANGUAGES),
            "emission": probe_emission(),
            "module_enumeration": probe_module_enumeration(directory),
            "lifting": probe_lifting(directory),
            "subset_boundary": probe_subset_boundary(directory),
        }
    both = [
        language
        for language in COMPLETE_MATRIX_LANGUAGES
        if report["emission"][language] == "SUPPORTED" and report["lifting"][language] == "SUPPORTED"
    ]
    neither = [
        language
        for language in COMPLETE_MATRIX_LANGUAGES
        if report["emission"][language].startswith("REJECTED")
        and report["lifting"][language].startswith("REJECTED")
    ]
    report["summary"] = {
        "bidirectional": both,
        "neither_direction": neither,
        # Only counted where both directions were actually probed here.
        "routes_between_bidirectional": len(both) * (len(both) - 1),
    }
    report["declaration_cross_check"] = _cross_check(report)
    return report


def _cross_check(report: dict[str, Any]) -> dict[str, Any]:
    """Does the inventory's declared route count match what just executed?

    `routes/inventory.json` publishes `limited_route_count` as the number of
    routes whose two endpoints both work. This recomputes it from probes that
    actually ran. The two agreeing is the point: a divergence means one of them
    is stale, and until now nothing would have said which.

    Only meaningful on a machine where every language could be probed -- a run
    full of NOT_PROBED has nothing to compare, and says so rather than
    reporting a mismatch it cannot substantiate.
    """
    inventory_path = Path(__file__).resolve().parents[3] / "routes" / "inventory.json"
    if not inventory_path.is_file():
        return {"status": "NOT_PROBED:INVENTORY_ABSENT", "path": str(inventory_path)}
    if any(verdict.startswith("NOT_PROBED") for verdict in report["lifting"].values()):
        return {
            "status": "NOT_PROBED:INCOMPLETE_RUN",
            "detail": "some languages could not be probed here, so the count is not comparable",
        }
    declared = json.loads(inventory_path.read_text(encoding="utf-8")).get("limited_route_count")
    executed = report["summary"]["routes_between_bidirectional"]
    return {
        "status": "MATCH" if declared == executed else "MISMATCH",
        "declared_limited_route_count": declared,
        "executed_bidirectional_routes": executed,
    }


def _table(report: dict[str, Any]) -> str:
    width = max(len(item) for item in report["emission"].values())
    width = max(width, max(len(item) for item in report["module_enumeration"].values()))
    lines = [
        f"{'language':<12} {'emission':<{width}} {'module-enumeration':<{width}} lifting",
        "-" * (14 + width * 2 + 40),
    ]
    for language in report["declared_languages"]:
        lines.append(
            f"{language:<12} {report['emission'][language]:<{width}} "
            f"{report['module_enumeration'][language]:<{width}} {report['lifting'][language]}"
        )
    construct_width = max(len(item) for item in report["subset_boundary"])
    lines += ["", f"{'construct':<{construct_width}} verdict", "-" * (construct_width + 44)]
    for construct, verdict in report["subset_boundary"].items():
        lines.append(f"{construct:<{construct_width}} {verdict}")
    summary = report["summary"]
    check = report["declaration_cross_check"]
    if check["status"] == "MATCH":
        cross = f"MATCH  declared={check['declared_limited_route_count']} executed={check['executed_bidirectional_routes']}"
    elif check["status"] == "MISMATCH":
        cross = (
            f"MISMATCH  inventory declares {check['declared_limited_route_count']}, "
            f"this run executed {check['executed_bidirectional_routes']}"
        )
    else:
        cross = check["status"]
    lines += [
        "",
        f"bidirectional here : {summary['bidirectional']}",
        f"neither direction  : {summary['neither_direction']}",
        f"routes between them: {summary['routes_between_bidirectional']}",
        f"vs inventory.json  : {cross}",
        "",
        "NOT_PROBED means this machine lacks the pinned toolchain. It is an",
        "instruction to re-run on a machine that has it, never a capability claim.",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the machine-readable report")
    arguments = parser.parse_args()
    report = run()
    if arguments.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_table(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
