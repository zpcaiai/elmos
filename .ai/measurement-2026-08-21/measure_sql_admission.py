"""ELMOS SQL dialect-conversion admission measurement.

`engines/sql-dialect-engine` already ships the right instrument --
`scan.scan_repository` parses every statement with the real certified parser
and reports IN_SUBSET / OUT_OF_SUBSET / SCAN_ERROR against a blocker
catalogue.  Its only dependency is `sqlglot==30.14.0` and its toolchain pin is
a library version, not a host path, so unlike the polyglot engine it carries
full toolchain attestation wherever it runs.

This script adds the corpus and three things the single headline coverage
number hides:

1. **File-level parse failures.**  When the pinned parser cannot tokenise a
   file at all, `scan_repository` records ONE `CERTIFIED_DDL_PARSE_FAILED`
   finding for the whole file.  An 87 KB schema then contributes 1 to the
   denominator, not several hundred.  Rolling that into a percentage makes
   the hardest files nearly invisible, so they are counted and reported
   separately here.

2. **DDL vs DML.**  A dump that carries seed data puts thousands of INSERTs in
   the denominator.  They are legitimately out of a DDL profile's scope but
   they swamp the ratio, so coverage is reported both over all statements and
   over schema statements only.

3. **count vs distinct_reasons.**  The engine's own caveat: one copy-pasted
   idiom can dominate an occurrence count.  Both are carried through.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

import sqlglot

from elmos_sql_dialect.models import Dialect
from elmos_sql_dialect.scan import discover_sql_files, report_to_dict, scan_repository
from elmos_sql_dialect.toolchains import PINNED_SQLGLOT_VERSION, verify_toolchain

#: sqlglot node type names that represent schema definition rather than data or
#: session state. Everything else (Insert, Select, Update, Delete, Command, ...)
#: is data/session traffic for the purposes of a DDL coverage ratio.
DDL_KINDS = frozenset({"Create", "Alter", "Drop", "Index", "Comment", "Truncate"})


def file_parse_status(path: Path, dialect: Dialect) -> dict:
    """Can the pinned parser split this file at all?"""
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stderr(buffer):
            statements = sqlglot.parse(path.read_text(encoding="utf-8"), read=dialect.value)
    except Exception as error:
        return {
            "file": path.name,
            "bytes": path.stat().st_size,
            "status": "FILE_PARSE_FAILED",
            "error": f"{type(error).__name__}: {str(error).splitlines()[0][:160]}",
            "statements": 0,
        }
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "status": "PARSED",
        "statements": sum(1 for item in statements if item is not None),
    }


def measure_corpus(name: str, root: Path, dialect: Dialect) -> dict:
    buffer = io.StringIO()
    with contextlib.redirect_stderr(buffer):
        report = report_to_dict(
            scan_repository(root, dialect, examples_per_blocker=5, include_all_findings=True)
        )

    files = [file_parse_status(path, dialect) for path in discover_sql_files(root)]
    unparseable = [item for item in files if item["status"] == "FILE_PARSE_FAILED"]

    ddl_in = ddl_blocked = dml_in = dml_blocked = 0
    kinds: Counter[str] = Counter()
    for finding in report["findings"]:
        kind = finding.get("statement_kind")
        if finding["status"] == "SCAN_ERROR":
            continue
        if kind is None:
            continue  # a whole-file parse failure, counted separately below
        kinds[kind] += 1
        is_ddl = kind in DDL_KINDS
        if finding["status"] == "IN_SUBSET":
            if is_ddl:
                ddl_in += 1
            else:
                dml_in += 1
        else:
            if is_ddl:
                ddl_blocked += 1
            else:
                dml_blocked += 1

    ddl_total = ddl_in + ddl_blocked
    return {
        "corpus": name,
        "source_dialect": dialect.value,
        "files": {
            "total": len(files),
            "parsed": len(files) - len(unparseable),
            "parse_failed": len(unparseable),
            "parse_failed_detail": unparseable,
            "parse_failed_bytes": sum(item["bytes"] for item in unparseable),
        },
        "totals": report["totals"],
        "coverage": {
            "all_statements": report["upper_bound_coverage"],
            "schema_statements_only": round(ddl_in / ddl_total, 4) if ddl_total else None,
            "schema_statements": ddl_total,
            "schema_in_subset": ddl_in,
            "data_and_session_statements": dml_in + dml_blocked,
        },
        "statement_kinds": dict(kinds.most_common(15)),
        "blockers": [
            {
                key: blocker[key]
                for key in ("reason_code", "family", "count", "distinct_reasons", "share_of_blocked")
            }
            for blocker in report["blockers"]
        ],
        "blocker_examples": {
            blocker["reason_code"]: blocker["example_statements"][:3]
            for blocker in report["blockers"][:6]
        },
        "caveats": report["caveats"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", action="append", required=True, metavar="NAME=PATH=DIALECT")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    verify_toolchain()  # fails closed unless sqlglot is the exact pinned release

    corpora = []
    for raw in arguments.corpus:
        name, path, dialect_name = raw.split("=", 2)
        print(f"[scan] {name} ({dialect_name})", file=sys.stderr, flush=True)
        corpora.append(measure_corpus(name, Path(path).resolve(strict=True), Dialect(dialect_name)))

    merged: dict[str, dict] = {}
    for corpus in corpora:
        for blocker in corpus["blockers"]:
            entry = merged.setdefault(
                blocker["reason_code"],
                {"family": blocker["family"], "count": 0, "distinct_reasons": 0},
            )
            entry["count"] += blocker["count"]
            entry["distinct_reasons"] += blocker["distinct_reasons"]

    schema_total = sum(c["coverage"]["schema_statements"] for c in corpora)
    schema_in = sum(c["coverage"]["schema_in_subset"] for c in corpora)
    all_in = sum(c["totals"]["inSubset"] for c in corpora)
    all_blocked = sum(c["totals"]["outOfSubset"] for c in corpora)
    blocked_total = sum(entry["count"] for entry in merged.values()) or 1

    report = {
        "kind": "elmos.sql-dialect-admission-measurement",
        "schema_version": "1.0.0",
        "profile": "certified-ddl-v1 + certified-alter-v1",
        "instrument": "elmos_sql_dialect.scan.scan_repository",
        "toolchain": {
            "sqlglot": PINNED_SQLGLOT_VERSION,
            "status": "PINNED_VERIFIED",
            "note": (
                "This engine pins a library version, not a host path, so the measurement "
                "carries the same toolchain attestation anywhere it runs -- unlike "
                "engines/polyglot-route-engine, which refuses off Darwin/arm64."
            ),
        },
        "aggregate": {
            "corpora": len(corpora),
            "files_total": sum(c["files"]["total"] for c in corpora),
            "files_parse_failed": sum(c["files"]["parse_failed"] for c in corpora),
            "files_parse_failed_bytes": sum(c["files"]["parse_failed_bytes"] for c in corpora),
            "statements_all": all_in + all_blocked,
            "in_subset_all": all_in,
            "coverage_all_statements": (
                round(all_in / (all_in + all_blocked), 4) if (all_in + all_blocked) else None
            ),
            "schema_statements": schema_total,
            "schema_in_subset": schema_in,
            "coverage_schema_statements_only": (
                round(schema_in / schema_total, 4) if schema_total else None
            ),
            "scan_errors": sum(c["totals"]["scanErrors"] for c in corpora),
            "blockers": [
                {"reason_code": code, **value, "share_of_blocked": round(value["count"] / blocked_total, 4)}
                for code, value in sorted(merged.items(), key=lambda i: (-i[1]["count"], i[0]))
            ],
        },
        "corpora": corpora,
        "limitations": [
            "UPPER BOUND from the source side. Target-side emission can still refuse a "
            "statement that parsed into the subset.",
            "A file the pinned parser cannot tokenise contributes ONE blocked finding, not "
            "one per statement. Read files_parse_failed alongside any percentage.",
            "Counts are exact, not sampled.",
            "Rank by distinct_reasons, not count.",
            "This measures the certified DDL/ALTER subset of engines/sql-dialect-engine. It "
            "says nothing about the Batch 31 typed transpiler or the ChinaDB targets.",
        ],
    }

    text = json.dumps(report, indent=2, ensure_ascii=False)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
        print(f"wrote {arguments.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
