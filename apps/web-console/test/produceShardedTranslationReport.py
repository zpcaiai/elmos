"""Produce a real two-shard conversion report for the Web contract test."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from elmos_polyglot_route.conversion_reporting import (
    _digest,
    _report_id,
    render_conversion_markdown,
    write_conversion_reports,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def block(obligation_id: str, direction: str, language: str, path: str, snippet: str) -> dict[str, object]:
    encoded = snippet.encode("utf-8")
    return {
        "block_id": f"{obligation_id}:{direction}-001",
        "path": path,
        "language": language,
        "symbol_id": f"function_{obligation_id[3:8]}",
        "document_bytes": len(encoded),
        "document_sha256": digest(snippet),
        "block_sha256": digest(snippet),
        "range": {
            "start_byte": 0,
            "end_byte": len(encoded),
            "start_line": 1,
            "start_column": 1,
            "end_line": 3,
            "end_column": 1,
        },
        "snippet": snippet,
        "truncated": False,
        "omission_reason": None,
        "extraction_method": (
            "PYTHON_AST_FUNCTION" if language == "python" else "NAME_ANCHORED_DOCUMENT_EXCERPT"
        ),
    }


def main() -> None:
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    functions: list[dict[str, object]] = []
    for sequence in range(1, 2_002):
        work_unit_id = f"WU-{sequence:05d}"
        obligation_id = f"{work_unit_id}:FO-001"
        name = f"function_{sequence:05d}"
        source = f"def {name}(value: int) -> int:\n    return value\n"
        target = f"export function {name}(value: number): number {{\n  return value;\n}}\n"
        source_block = block(obligation_id, "SOURCE", "python", f"src/{name}.py", source)
        target_block = block(
            obligation_id,
            "TARGET",
            "typescript",
            f"batch/units/{work_unit_id}/migrated.ts",
            target,
        )
        functions.append(
            {
                "obligation_id": obligation_id,
                "work_unit_id": work_unit_id,
                "kind": "CALLABLE",
                "functional_description": {
                    "text": f"Callable signature in src/{name}.py: {name}(value: int) -> int",
                    "source": "AST_SIGNATURE_DERIVED",
                },
                "status": "VERIFIED",
                "source_blocks": [source_block],
                "target_blocks": [target_block],
                "mapping": {
                    "mapping_id": f"{obligation_id}:MAP-001",
                    "kind": "SYNTHESIZED",
                    "freshness": "FRESH",
                    "confidence": 0.7,
                    "source_block_ids": [source_block["block_id"]],
                    "target_block_ids": [target_block["block_id"]],
                    "provenance_refs": ["repository-route-plan.json"],
                },
                "evidence_refs": ["repository-route-plan.json", "batch/batch-report.json"],
                "failure": None,
                "improvement_actions": [],
            }
        )
    count = len(functions)
    cases_digest = digest("web-real-producer-sharded-cases")
    report: dict[str, object] = {
        "schema_version": "1.0.0",
        "kind": "elmos.project-language-conversion-report",
        "report_id": "sha256:pending",
        "status": "COMPLETE",
        "repository": {
            "reference": "local:web-real-producer-sharded",
            "snapshot_sha256": digest("web-real-producer-sharded-snapshot"),
        },
        "route": {
            "route_id": "python-to-typescript",
            "source_language": "python",
            "target_language": "typescript",
            "profile": "typed-pure-function-v1",
        },
        "metric": {
            "definition_id": "verified-functional-obligation-success-rate/v1",
            "measurement_unit": "FUNCTIONAL_OBLIGATION",
            "comparison_basis": "DECLARED_BEHAVIOR_ORACLE",
            "numerator": count,
            "denominator": count,
            "exact_fraction": f"{count}/{count}",
            "success_rate_basis_points": 10_000,
            "display_percent": "100.00%",
            "measurement_status": "MEASURED",
            "denominator_complete": True,
            "reported_obligation_count": count,
            "unknown_scope_count": 0,
            "unreported_obligation_count": 0,
            "project_success_rate_lower_bound_basis_points": 10_000,
            "project_success_rate_upper_bound_basis_points": 10_000,
            "project_success_rate_display": "100.00%",
            "formula": "VERIFIED functional obligations / compiler-completely inventoried functional obligations",
        },
        "status_counts": dict(Counter(item["status"] for item in functions)),
        "code_artifact_ready": True,
        "functions": functions,
        "exclusions": [],
        "blockers": [],
        "build_verification": {"status": "PASSED", "reason": None},
        "evidence_boundary": {
            "local_target_build": "PASSED",
            "target_behavior_oracle": "PASSED_PER_VERIFIED_FUNCTION",
            "source_target_declared_case_equivalence": "PASSED_PER_VERIFIED_FUNCTION",
            "source_target_runtime_equivalence": "NOT_RUN",
            "independent_verification": "NOT_RUN",
            "external_verification": "NOT_RUN",
            "cases_manifest_sha256": cases_digest,
        },
        "markdown_renderer_version": "elmos-functional-conversion-markdown/v1",
        "markdown_sha256": "0" * 64,
        "certification_status": "NOT_CERTIFIED",
    }
    report["report_id"] = _report_id(report)
    report["markdown_sha256"] = _digest(render_conversion_markdown(report).encode("utf-8"))
    summary = write_conversion_reports(report, output)
    (output / "web-test-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
