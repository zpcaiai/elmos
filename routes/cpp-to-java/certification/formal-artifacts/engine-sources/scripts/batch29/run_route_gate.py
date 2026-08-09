#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from validate_route import (
    sha256_file,
    strict_evidence_requested,
    validate_formal_equivalence,
    validate_module_equivalence,
)
from route_sets import EVIDENCED_ROUTE_KEYS, SPECIALIZED_ROUTE_KEYS, split_route_key


SPECIALIZED_NEGATIVE_CASES = {
    "java": {"java-int-width", "java-string-raw-reference-equality"},
    "cpp": {"cpp-long-width", "cpp-unsigned-domain"},
    "objc": {"objc-nsinteger-width", "objc-nsstring-pointer-identity"},
    "swift": {"swift-int-requires-int64", "swift-helper-tamper"},
}
SPECIALIZED_COMMON_NEGATIVE_CASES = {
    "specialized-string-semantics-unsupported",
    "specialized-number-arithmetic-unsupported",
    "specialized-non-finite-case-unsupported",
    "specialized-overflow-outside-no-error-domain",
    "undeclared-directed-route-fails-closed",
    "missing-symbol-fails-closed",
}
SPECIALIZED_NEGATIVE_REASON_CODES = {
    "java-int-width": {"JAVA_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:int"},
    "java-string-raw-reference-equality": {
        "JAVA_STRING_REFERENCE_EQUALITY_OUTSIDE_CERTIFIED_SUBSET"
    },
    "cpp-long-width": {"CPP_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:long"},
    "cpp-unsigned-domain": {
        "CPP_UNSUPPORTED_TYPE:unsigned long long",
        "CPP_UNSIGNED",
    },
    "objc-nsinteger-width": {
        "OBJC_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:NSInteger"
    },
    "objc-nsstring-pointer-identity": {
        "OBJC_STRING_POINTER_COMPARISON_OUTSIDE_CERTIFIED_SUBSET"
    },
    "swift-int-requires-int64": {
        "SWIFT_INTEGER_WIDTH_OUTSIDE_CERTIFIED_SUBSET:Int"
    },
    "swift-helper-tamper": {"EMITTED_HELPER_SOURCE_MISMATCH:swift"},
    "undeclared-directed-route-fails-closed": {
        "UNSUPPORTED_DIRECTED_ROUTE:java-to-swift"
    },
    "missing-symbol-fails-closed": {"FUNCTION_NOT_FOUND", "NO_SUPPORTED_FUNCTIONS"},
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def has_file(path: Path) -> bool:
    return any(item.is_file() for item in path.rglob("*"))


def require_metric(
    failures: list[str],
    metrics: dict[str, Any],
    name: str,
    *,
    minimum: float,
) -> None:
    value = metrics.get(name)
    if not isinstance(value, int | float) or value < minimum:
        failures.append(f"{name} must be >= {minimum}")


def require_zero(failures: list[str], evidence: dict[str, Any], name: str) -> None:
    if evidence.get(name) != 0:
        failures.append(f"{name} must be zero")


def validate_independent_corpus(
    failures: list[str],
    route: Path,
    corpus: str,
) -> None:
    root = route / "corpus" / corpus
    if not has_file(root):
        failures.append(f"{corpus} corpus is empty")
        return
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        failures.append(f"{corpus} manifest is missing")
        return
    manifest = load(manifest_path)
    if manifest.get("corpus") != corpus:
        failures.append(f"{corpus} manifest corpus does not match")
    if manifest.get("independent") is not True:
        failures.append(f"{corpus} corpus is not marked independent")
    if manifest.get("rule_authoring_input") is not False:
        failures.append(f"{corpus} corpus was used for rule authoring")
    for field in ("source_file", "cases_file"):
        relative = manifest.get(field)
        if not isinstance(relative, str) or not (root / relative).is_file():
            failures.append(f"{corpus} {field} is missing")


def validate_evidence_refs(
    failures: list[str],
    route: Path,
    evidence: dict[str, Any],
) -> None:
    runs = evidence.get("runs")
    if not isinstance(runs, list) or not runs:
        failures.append("evidence runs are empty")
        return
    for reference in runs:
        if not isinstance(reference, str):
            failures.append("evidence run reference is invalid")
            continue
        path = route / reference
        if not path.is_file():
            failures.append(f"evidence run is missing: {reference}")
            continue
        run = load(path)
        if run.get("status") != "PASSED":
            failures.append(f"evidence run did not pass: {reference}")
        if run.get("behavior_pass_rate") != 1.0:
            failures.append(f"behavior pass rate is not 1: {reference}")
        if run.get("critical_unknown_semantics") != 0:
            failures.append(f"critical unknown semantics remain: {reference}")
        if run.get("source_map_coverage") != 1.0:
            failures.append(f"source-map coverage is not 1: {reference}")


def validate_negative_refs(
    failures: list[str], route: Path, evidence: dict[str, Any]
) -> None:
    references = evidence.get("negative_runs")
    if not isinstance(references, list) or not references:
        failures.append("negative evidence runs are empty")
        return
    for reference in references:
        if not isinstance(reference, str) or not (route / reference).is_file():
            failures.append(f"negative evidence run is missing: {reference}")
            continue
        result = load(route / reference)
        if (
            result.get("status") != "PASSED"
            or result.get("expected_result") != "BLOCKED"
        ):
            failures.append(f"negative evidence did not fail closed: {reference}")
        if result.get("test_integrity") != "PRESERVED":
            failures.append(f"negative test integrity is invalid: {reference}")
        if route.name not in SPECIALIZED_ROUTE_KEYS:
            continue
        source, target = split_route_key(route.name)
        expected_case_ids = {
            *SPECIALIZED_NEGATIVE_CASES[source],
            *SPECIALIZED_NEGATIVE_CASES[target],
            *SPECIALIZED_COMMON_NEGATIVE_CASES,
        }
        cases = result.get("cases")
        if not isinstance(cases, list):
            failures.append(f"specialized negative cases are missing: {reference}")
            continue
        observed_case_ids = {
            item.get("case_id") for item in cases if isinstance(item, dict)
        }
        if len(cases) != len(expected_case_ids) or observed_case_ids != expected_case_ids:
            failures.append(f"specialized negative case set is not exact: {reference}")
        for index, item in enumerate(cases):
            if not isinstance(item, dict):
                failures.append(f"specialized negative case is invalid: {reference}:{index}")
                continue
            if (
                item.get("status") != "PASSED"
                or item.get("expected_result") != "BLOCKED"
                or not isinstance(item.get("observed_reason"), str)
                or not item.get("observed_reason")
            ):
                failures.append(
                    f"specialized negative case did not fail closed: {reference}:{index}"
                )
            case_id = item.get("case_id")
            route_specific_codes = {
                "specialized-string-semantics-unsupported": {
                    f"SPECIALIZED_STRING_SEMANTICS_UNSUPPORTED:{route.name}"
                },
                "specialized-number-arithmetic-unsupported": {
                    f"SPECIALIZED_NUMBER_ARITHMETIC_UNSUPPORTED:{route.name}:addNumber"
                },
                "specialized-non-finite-case-unsupported": {
                    "SPECIALIZED_CASE_NON_FINITE_NUMBER_UNSUPPORTED:"
                    f"{route.name}:echoNumber:0"
                },
                "specialized-overflow-outside-no-error-domain": {
                    "SPECIALIZED_CASE_OUTSIDE_CANONICAL_NO_ERROR_DOMAIN:"
                    f"{route.name}:calculate:0:IntegerOverflow"
                },
            }
            expected_codes = route_specific_codes.get(
                case_id, SPECIALIZED_NEGATIVE_REASON_CODES.get(case_id, set())
            )
            if item.get("observed_reason") not in expected_codes:
                failures.append(
                    f"specialized negative reason code is not exact: {reference}:{index}"
                )
            input_refs = item.get("input_refs")
            if not isinstance(input_refs, list) or not input_refs:
                failures.append(
                    f"specialized negative case has no byte-bound input: {reference}:{index}"
                )
                continue
            for input_index, input_ref in enumerate(input_refs):
                if not isinstance(input_ref, dict):
                    failures.append(
                        f"specialized negative input is invalid: {reference}:{index}:{input_index}"
                    )
                    continue
                relative = input_ref.get("path")
                if (
                    not isinstance(relative, str)
                    or Path(relative).is_absolute()
                    or ".." in Path(relative).parts
                ):
                    failures.append(
                        f"specialized negative input path is unsafe: {reference}:{index}:{input_index}"
                    )
                    continue
                path = route / relative
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or input_ref.get("sha256") != sha256_file(path)
                    or input_ref.get("bytes") != path.stat().st_size
                ):
                    failures.append(
                        f"specialized negative input digest drift: {reference}:{index}:{input_index}"
                    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("route_dir")
    args = parser.parse_args()
    route = Path(args.route_dir)
    try:
        manifest = load(route / "route.json")
    except Exception as exc:
        print(f"GATE FAIL: route manifest is unreadable: {exc}", file=sys.stderr)
        return 2
    route_key = manifest.get("route_key")
    if route.name != route_key:
        print("GATE FAIL: route directory name does not match route_key", file=sys.stderr)
        return 2
    if route_key not in EVIDENCED_ROUTE_KEYS:
        print("GATE FAIL: route_key is outside the explicit allowlist", file=sys.stderr)
        return 2
    source, target = split_route_key(str(route_key))
    if (
        manifest.get("source", {}).get("language") != source
        or manifest.get("target", {}).get("language") != target
    ):
        print("GATE FAIL: route source/target tuple does not match route_key", file=sys.stderr)
        return 2
    validator = Path(__file__).with_name("validate_route.py")
    if subprocess.run(
        [sys.executable, str(validator), str(route)], check=False
    ).returncode:
        return 1

    evidence = load(route / "certification" / "evidence.json")
    certification = load(route / "certification" / "certification.json")
    support = load(route / "support-matrix.json")
    status = str(manifest.get("status", "")).lower()
    certification_status = str(certification.get("status", "")).lower()
    failures: list[str] = []

    if route_key in SPECIALIZED_ROUTE_KEYS:
        profiles = manifest.get("profiles", {})
        gates = manifest.get("gates", {})
        if profiles.get("input_domain") != "canonical-finite-no-error-input-domain":
            failures.append("specialized input domain drift")
        if profiles.get("module_profile") != "typed-pure-module-v1":
            failures.append("specialized module profile drift")
        for field in (
            "module_equivalence_required",
            "concrete_spans_required",
            "canonical_finite_no_error_input_domain_required",
        ):
            if gates.get(field) is not True:
                failures.append(f"specialized gate {field} must be true")
        if gates.get("specialized_string_semantics_allowed") is not False:
            failures.append("specialized string semantics must remain blocked")
        mappings = load(route / "mappings" / "types.json")
        if mappings.get("types") != ["integer", "number", "boolean"]:
            failures.append("specialized type mapping must be exact integer/number/boolean")
        if mappings.get("input_domain") != "canonical-finite-no-error-input-domain":
            failures.append("specialized type mapping input domain drift")
        if mappings.get("string_semantics") != "BLOCK":
            failures.append("specialized type mapping does not block string")
        lowering = load(route / "lowering" / "profile.json")
        if lowering.get("input_domain") != "canonical-finite-no-error-input-domain":
            failures.append("specialized lowering input domain drift")
        if lowering.get("concrete_spans_required") is not True:
            failures.append("specialized lowering must require concrete spans")
        domains = lowering.get("operator_domains", {})
        if domains.get("number_arithmetic") != {
            "operators": [],
            "blocked_operators": ["+", "-", "*", "/", "%"],
            "status": "BLOCKED",
        }:
            failures.append("specialized number arithmetic policy drift")
        expected_types = {
            "development": ["integer"],
            "holdout": ["number"],
            "real-repository": ["boolean"],
        }
        for corpus, type_coverage in expected_types.items():
            corpus_manifest = load(route / "corpus" / corpus / "manifest.json")
            if corpus_manifest.get("type_coverage") != type_coverage:
                failures.append(f"specialized {corpus} type coverage drift")
            if (
                corpus_manifest.get("input_domain")
                != "canonical-finite-no-error-input-domain"
            ):
                failures.append(f"specialized {corpus} input domain drift")
        if evidence.get("evidenced_type_coverage") != [
            "integer",
            "number",
            "boolean",
        ]:
            failures.append("specialized evidence type coverage drift")
        if evidence.get("input_domain") != "canonical-finite-no-error-input-domain":
            failures.append("specialized evidence input domain drift")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            failures.append("specialized route must remain NOT_CERTIFIED")

    if certification_status != status:
        failures.append("route and certification statuses must match")
    if not manifest.get("maintenance_owner"):
        failures.append("maintenance owner is missing")
    if not manifest.get("review_date"):
        failures.append("review date is missing")

    capabilities = support.get("capabilities", [])
    if status in {"limited", "certified"}:
        supported_status = "certified" if status == "certified" else "supported"
        scoped = [
            capability
            for capability in capabilities
            if capability.get("status") == supported_status
        ]
        if not scoped:
            failures.append(f"{status} route has no {supported_status} capabilities")
        for capability in scoped:
            if not capability.get("evidence_refs"):
                failures.append(
                    f"{supported_status} capability lacks evidence: {capability.get('id')}"
                )

        metrics = evidence.get("metrics", {})
        require_metric(failures, metrics, "build_green_rate", minimum=1.0)
        require_metric(failures, metrics, "p0_behavior_pass_rate", minimum=1.0)
        require_metric(failures, metrics, "source_map_coverage", minimum=0.95)
        for name in ("manual_hours", "cost_per_verified_workload"):
            value = metrics.get(name)
            if not isinstance(value, int | float) or value < 0:
                failures.append(f"{name} must be a non-negative number")
        for field in (
            "critical_unknown_semantics",
            "critical_behavior_regressions",
            "test_integrity_violations",
        ):
            require_zero(failures, evidence, field)
        if evidence.get("execution_status") != "PASSED_LOCAL":
            failures.append("local execution evidence did not pass")
        validate_independent_corpus(failures, route, "holdout")
        validate_independent_corpus(failures, route, "real-repository")
        validate_evidence_refs(failures, route, evidence)
        validate_negative_refs(failures, route, evidence)

    strict_requested = strict_evidence_requested(certification)
    if strict_requested:
        formal_equivalence, strict_failures = validate_formal_equivalence(
            route, manifest, certification
        )
        failures.extend(strict_failures)
        if formal_equivalence is None:
            failures.append("strict formal-equivalence evidence is missing")
        else:
            semantic_ir = formal_equivalence.get("semantic_ir", {})
            if semantic_ir.get("status") != "PASSED":
                failures.append("semantic IR equivalence did not pass")
            if semantic_ir.get("source_ir_sha256") != semantic_ir.get(
                "target_relift_ir_sha256"
            ):
                failures.append("source and target re-lift semantic IR digests differ")
            if semantic_ir.get("unknown_or_dropped_nodes") != 0:
                failures.append("semantic IR contains unknown or dropped nodes")
            if semantic_ir.get("differences") != []:
                failures.append("semantic IR differences remain")

            semantic_chunks = formal_equivalence.get("semantic_chunks", {})
            if semantic_chunks.get("status") != "PASSED":
                failures.append("semantic chunk equivalence did not pass")
            if semantic_chunks.get("matched") != semantic_chunks.get("total"):
                failures.append("not every semantic chunk is matched")
            if semantic_chunks.get("unmatched") != 0:
                failures.append("unmatched semantic chunks remain")
            if semantic_chunks.get("ambiguous") != 0:
                failures.append("ambiguous semantic chunks remain")
            if semantic_chunks.get("coverage") != 1.0:
                failures.append("semantic chunk coverage is not 1")
            if any(
                chunk.get("status") != "MATCHED"
                for chunk in semantic_chunks.get("chunks", [])
                if isinstance(chunk, dict)
            ):
                failures.append("a semantic chunk is not matched")

            behavior = formal_equivalence.get("behavior_equivalence", {})
            if behavior.get("status") != "PASSED":
                failures.append("behavior equivalence did not pass")
            if behavior.get("passed_cases") != behavior.get("total_cases"):
                failures.append("not every behavior-equivalence case passed")
            if behavior.get("counterexamples") != []:
                failures.append("behavior-equivalence counterexamples remain")
            for field in (
                "canonical_oracle_passed",
                "source_runtime_passed",
                "target_runtime_passed",
            ):
                if behavior.get(field) is not True:
                    failures.append(f"behavior equivalence {field} is not true")

            proof = formal_equivalence.get("formal_proof", {})
            proof_status = proof.get("status")
            if proof_status == "COUNTEREXAMPLE":
                failures.append("formal proof produced a counterexample")
            elif proof_status == "PROVED":
                pass
            elif proof_status == "PROVED_UNDER_ASSUMPTIONS":
                if not proof.get("assumptions"):
                    failures.append(
                        "PROVED_UNDER_ASSUMPTIONS lacks explicit assumptions"
                    )
                if status == "certified":
                    failures.append("assumption-bound proof cannot certify a route")
                if certification.get("certification_decision") != "NOT_CERTIFIED":
                    failures.append("assumption-bound proof must remain NOT_CERTIFIED")
            else:
                failures.append(f"formal proof status is non-passing: {proof_status}")

    module_equivalence, module_failures = validate_module_equivalence(
        route, manifest, certification
    )
    failures.extend(module_failures)
    module_required = manifest.get("gates", {}).get("module_equivalence_required") is True
    if module_required:
        if evidence.get("module_execution_status") != "PASSED_LOCAL":
            failures.append("module execution status is not PASSED_LOCAL")
        if certification.get("gate_results", {}).get("module_execution") != "PASSED":
            failures.append("module execution gate is not PASSED")
        if module_equivalence is None:
            failures.append("required module equivalence was not evaluated")
        else:
            if module_equivalence.get("status") != "PASSED":
                failures.append(
                    f"module equivalence is non-passing: {module_equivalence.get('status')}"
                )
            functions = module_equivalence.get("functions")
            minimum = manifest.get("gates", {}).get("minimum_module_functions", 3)
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 3:
                minimum = 3
            if not isinstance(functions, list) or len(functions) < minimum:
                failures.append(
                    f"module equivalence must cover at least {minimum} functions"
                )
            elif status == "certified" and any(
                item.get("layers", {}).get("formal", {}).get("status") != "PROVED"
                for item in functions
                if isinstance(item, dict)
            ):
                failures.append(
                    "certified module route requires unconditional PROVED evidence for every function"
                )

    gate_results = certification.get("gate_results", {})
    if status == "limited":
        if gate_results.get("local_execution") != "PASSED":
            failures.append("limited route requires local execution PASSED")
        if gate_results.get("independent_verification") not in {"NOT_RUN", "PASSED"}:
            failures.append("limited route has invalid independent verification state")
        if gate_results.get("external_execution") not in {"NOT_RUN", "PASSED"}:
            failures.append("limited route has invalid external execution state")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            failures.append("limited route must remain NOT_CERTIFIED")

    if status == "certified":
        if gate_results.get("independent_verification") != "PASSED":
            failures.append("certified route requires independent verification PASSED")
        if gate_results.get("external_execution") != "PASSED":
            failures.append("certified route requires external execution PASSED")
        if certification.get("certification_decision") != "CERTIFIED":
            failures.append("certified route requires certification_decision CERTIFIED")
        if strict_requested:
            proof_status = (
                formal_equivalence.get("formal_proof", {}).get("status")
                if formal_equivalence is not None
                else None
            )
            if proof_status != "PROVED":
                failures.append(
                    "certified strict route requires unconditional PROVED evidence"
                )

    if failures:
        print(
            "\n".join(f"GATE FAIL: {failure}" for failure in failures),
            file=sys.stderr,
        )
        return 2
    decision = "NOT_CERTIFIED" if status != "certified" else "CERTIFIED"
    print(f"GATE PASS: {manifest.get('route_key')} status={status} decision={decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
