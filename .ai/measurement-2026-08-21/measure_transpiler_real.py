"""Batch 31 typed SQL transpiler -- real-query pass rate across all 42 routes.

`qualification.run_qualification` reports 248/248 eligible syntax cases and
44/44 fail-closed negatives.  That corpus is synthetic and self-declared as
such ("ELMOS synthetic development corpus", "real customer workload NOT_RUN").

This script drives the same `transpiler.transpile` entry point with queries the
engine has never seen: the 22 TPC-H benchmark queries, the industry-standard
realistic analytic workload.  Every one of the 42 declared directional routes
is attempted for every query, and each cell lands in exactly one bucket:

    SUPPORTED       transpiled, and the emission re-parsed under the target
    UNSUPPORTED     the engine refused -- a real, fail-closed boundary
    SOURCE_PARSE    the pinned parser could not read the source at all
    ENGINE_ERROR    neither of the above -- an engine defect, never a boundary

ENGINE_ERROR is kept separate on purpose: folding a crash into "unsupported"
would launder a defect into a coverage percentage.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from elmos_sql_transpiler.profiles import route_matrix
from elmos_sql_transpiler.transpiler import (
    ParseError,
    TokenError,
    TranspileRequest,
    UnsupportedError,
    transpile,
)


def classify(query_id: str, sql: str, source: str, target: str) -> tuple[str, str]:
    """`transpile` does NOT raise on refusal -- it RETURNS a result whose
    `state` is BLOCKED and whose `target_sql` is None, carrying diagnostics.

    Reading only exceptions therefore scores every refusal as a success. The
    first version of this script did exactly that and reported 924/924; the
    verdict must come from the returned state.
    """
    try:
        result = transpile(
            TranspileRequest(query_id=query_id, source_profile=source, target_profile=target, sql=sql)
        )
    except UnsupportedError as error:
        return "UNSUPPORTED", str(getattr(error, "code", type(error).__name__))
    except (ParseError, TokenError):
        return "SOURCE_PARSE", "ParserRaised"
    except Exception as error:  # engine defect, not a boundary
        return "ENGINE_ERROR", f"{type(error).__name__}: {str(error)[:120]}"

    codes = ",".join(
        sorted({str(getattr(item, "code", "")) for item in (result.diagnostics or ())} - {""})
    )
    if result.state == "BLOCKED" or result.target_sql is None:
        if getattr(result, "syntax_parse", None) == "FAILED":
            return "SOURCE_PARSE", codes or "SOURCE_PARSE_FAILED"
        return "UNSUPPORTED", codes or "BLOCKED"
    if result.metadata.get("silentFallbackUsed"):
        # The contract forbids permissive raw-command output; if it ever
        # appears it is a contract violation, not a pass.
        return "ENGINE_ERROR", "SILENT_FALLBACK_USED"
    if getattr(result, "target_reparse", None) not in {"PASSED", "OK", "PASS"}:
        return "UNSUPPORTED", f"TARGET_REPARSE:{getattr(result, 'target_reparse', None)}"
    return "SUPPORTED", ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", required=True, type=Path, help="directory of .sql files")
    parser.add_argument("--label", default="tpch-22")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    files = sorted(arguments.queries.glob("*.sql"))
    if not files:
        raise SystemExit("no .sql files found")
    routes = route_matrix()

    buckets: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    per_route: dict[str, Counter[str]] = {}
    per_query: dict[str, Counter[str]] = {}
    engine_errors: list[dict[str, str]] = []

    for route in routes:
        row: Counter[str] = Counter()
        for path in files:
            sql = path.read_text(encoding="utf-8").strip()
            query_id = path.stem
            bucket, reason = classify(query_id, sql, route.source_profile, route.target_profile)
            buckets[bucket] += 1
            row[bucket] += 1
            per_query.setdefault(query_id, Counter())[bucket] += 1
            if reason:
                reasons[f"{bucket}:{reason}"] += 1
            if bucket == "ENGINE_ERROR" and len(engine_errors) < 25:
                engine_errors.append({"route": route.id, "query": query_id, "error": reason})
        per_route[route.id] = row

    cells = sum(buckets.values())
    decided = buckets["SUPPORTED"] + buckets["UNSUPPORTED"]
    report = {
        "kind": "elmos.sql-transpiler-real-query-measurement",
        "schema_version": "1.0.0",
        "instrument": "elmos_sql_transpiler.transpiler.transpile",
        "corpus": {
            "label": arguments.label,
            "queries": len(files),
            "note": (
                "TPC-H benchmark queries, substitution points bound to literals. Not seen by "
                "the engine's synthetic development/holdout/representative corpora."
            ),
        },
        "routes": len(routes),
        "cells": cells,
        "buckets": dict(buckets.most_common()),
        "rates": {
            "supported_over_cells": round(buckets["SUPPORTED"] / cells, 4) if cells else None,
            "supported_over_decided": round(buckets["SUPPORTED"] / decided, 4) if decided else None,
            "engine_error_share": round(buckets["ENGINE_ERROR"] / cells, 4) if cells else None,
        },
        "top_reasons": dict(reasons.most_common(20)),
        "per_route": {
            route_id: dict(row.most_common()) for route_id, row in sorted(per_route.items())
        },
        "per_query": {
            query_id: dict(row.most_common()) for query_id, row in sorted(per_query.items())
        },
        "engine_errors_sample": engine_errors,
        "limitations": [
            "Syntax-level only: this transpiles and re-parses. No source execution, target "
            "execution or result equivalence was run -- those are NOT_RUN in the engine too.",
            "SUPPORTED means the engine produced target SQL that re-parsed, not that the two "
            "queries return the same rows.",
            "ENGINE_ERROR is a defect, never a subset boundary, and is excluded from "
            "supported_over_decided.",
        ],
    }

    text = json.dumps(report, indent=2)
    if arguments.output:
        arguments.output.write_text(text, encoding="utf-8")
        print(f"wrote {arguments.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
