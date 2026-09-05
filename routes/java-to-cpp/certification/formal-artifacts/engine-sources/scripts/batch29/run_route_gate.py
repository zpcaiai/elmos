#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

if __name__ == "__main__":
    from fresh_route_runtime import run_in_fresh_locked_runtime

    fresh_runtime_exit = run_in_fresh_locked_runtime(
        Path(__file__), sys.argv[1:]
    )
    if fresh_runtime_exit is not None:
        raise SystemExit(fresh_runtime_exit)

from route_sets import (
    CORE_ROUTE_KEYS,
    EVIDENCED_ROUTE_KEYS,
    MODULE_EQUIVALENCE_ROUTE_KEYS,
    NODEJS_EXACT_ROUTE_KEYS,
    SPECIALIZED_ROUTE_KEYS,
    V3_EXACT_ROUTE_KEYS,
    split_route_key,
)
from validate_route import (
    SWIFT_ANALYZER_RECEIPT_PATH,
    _validate_specialized_native_runtime_replay,
    strict_evidence_requested,
    validate_formal_equivalence,
    validate_module_equivalence,
    validate_nodejs_negative_evidence,
    validate_specialized_negative_evidence,
    validate_v3_research_route_contract,
)
from validate_route import (
    main as validate_route_main,
)


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
    failures: list[str],
    route: Path,
    evidence: dict[str, Any],
    *,
    replay_specialized: bool = True,
) -> None:
    if route.name in SPECIALIZED_ROUTE_KEYS:
        if replay_specialized:
            try:
                manifest = load(route / "route.json")
            except Exception as exc:
                failures.append(f"specialized negative route manifest is unreadable: {exc}")
                return
            validate_specialized_negative_evidence(
                route,
                manifest,
                evidence,
                failures,
            )
        return
    if route.name in NODEJS_EXACT_ROUTE_KEYS:
        try:
            manifest = load(route / "route.json")
        except Exception as exc:
            failures.append(f"Node.js negative route manifest is unreadable: {exc}")
            return
        validate_nodejs_negative_evidence(route, manifest, evidence, failures)
        return

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


def main() -> int:
    started = time.monotonic()
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
    specialized = route_key in SPECIALIZED_ROUTE_KEYS
    nodejs = route_key in NODEJS_EXACT_ROUTE_KEYS
    v3 = route_key in V3_EXACT_ROUTE_KEYS
    module_route = route_key in MODULE_EQUIVALENCE_ROUTE_KEYS
    if (
        manifest.get("source", {}).get("language") != source
        or manifest.get("target", {}).get("language") != target
    ):
        print("GATE FAIL: route source/target tuple does not match route_key", file=sys.stderr)
        return 2
    if v3:
        try:
            evidence = load(route / "certification" / "evidence.json")
            certification = load(route / "certification" / "certification.json")
            support = load(route / "support-matrix.json")
        except Exception as exc:
            print(f"GATE FAIL: V3 research contract is unreadable: {exc}", file=sys.stderr)
            return 2
        failures: list[str] = []
        validate_v3_research_route_contract(
            manifest,
            support,
            evidence,
            certification,
            failures,
        )
        status = str(manifest.get("status", "")).lower()
        if str(certification.get("status", "")).lower() != status:
            failures.append("route and certification statuses must match")
        if not manifest.get("maintenance_owner"):
            failures.append("maintenance owner is missing")
        if not manifest.get("review_date"):
            failures.append("review date is missing")
        if failures:
            print(
                "\n".join(f"GATE FAIL: {failure}" for failure in failures),
                file=sys.stderr,
            )
            print(f"GATE WALL: {time.monotonic() - started:.3f}s", file=sys.stderr)
            return 2
        print(
            f"GATE PASS: {route_key} status={status} "
            f"decision=NOT_CERTIFIED wall_seconds={time.monotonic() - started:.3f}"
        )
        return 0
    validator = Path(__file__).with_name("validate_route.py")
    original_argv = sys.argv[:]
    try:
        sys.argv = [str(validator), str(route)]
        validator_status = validate_route_main()
    finally:
        sys.argv = original_argv
    if validator_status:
        print(f"GATE WALL: {time.monotonic() - started:.3f}s", file=sys.stderr)
        return 1

    evidence = load(route / "certification" / "evidence.json")
    certification = load(route / "certification" / "certification.json")
    support = load(route / "support-matrix.json")
    status = str(manifest.get("status", "")).lower()
    certification_status = str(certification.get("status", "")).lower()
    failures: list[str] = []

    if specialized:
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
    if nodejs:
        profiles = manifest.get("profiles", {})
        gates = manifest.get("gates", {})
        if profiles.get("input_domain") != "nodejs-es2022-esm-safe-integer-finite-v1":
            failures.append("Node.js input domain drift")
        if profiles.get("module_profile") != "typed-pure-module-v1":
            failures.append("Node.js module profile drift")
        for field in (
            "module_equivalence_required",
            "concrete_spans_required",
            "nodejs_safe_integer_finite_domain_required",
        ):
            if gates.get(field) is not True:
                failures.append(f"Node.js gate {field} must be true")
        if gates.get("nodejs_effects_async_io_allowed") is not False:
            failures.append("Node.js async/I/O effects must remain blocked")
        nodejs_typescript = {source, target} == {"javascript", "typescript"}
        expected_types = (
            ["number", "boolean", "string"]
            if nodejs_typescript
            else ["integer", "number", "boolean"]
        )
        capability_by_id = {
            item.get("id"): item
            for item in support.get("capabilities", [])
            if isinstance(item, dict)
        }
        expected_capability_statuses = {
            "typed-pure-function-v1": "conditional",
            "primitive-types": "conditional",
            "nodejs-es2022-esm-safe-integer-finite-v1": "conditional",
            "string-semantics": "conditional" if nodejs_typescript else "blocked",
            "number-arithmetic": "blocked",
            "if-return-control-flow": "conditional",
            "framework-database-async-concurrency": "blocked",
            "typed-pure-module-v1": "conditional",
        }
        for capability_id, expected_status in expected_capability_statuses.items():
            if capability_by_id.get(capability_id, {}).get("status") != expected_status:
                failures.append(f"Node.js capability {capability_id} status drift")
        if gates.get("nodejs_typescript_integer_semantics_allowed") is not (
            not nodejs_typescript
        ):
            failures.append("Node.js/TypeScript integer gate drift")
        mappings = load(route / "mappings" / "types.json")
        if mappings.get("types") != expected_types:
            failures.append("Node.js type mapping drift")
        expected_string = (
            "STRICT_ECMASCRIPT_VALUE_EQUALITY_CONCAT"
            if nodejs_typescript
            else "BLOCK"
        )
        if mappings.get("string_semantics") != expected_string:
            failures.append("Node.js string mapping boundary drift")
        expected_integer = (
            "BLOCK_NO_EXPLICIT_INTEGER_TYPE"
            if nodejs_typescript
            else "SAFE_INTEGER_CONDITIONAL"
        )
        if mappings.get("integer_semantics") != expected_integer:
            failures.append("Node.js integer mapping boundary drift")
        lowering = load(route / "lowering" / "profile.json")
        if lowering.get("concrete_spans_required") is not True:
            failures.append("Node.js lowering must require concrete spans")
        if lowering.get("integer_semantics") != expected_integer:
            failures.append("Node.js integer lowering boundary drift")
        if evidence.get("evidenced_type_coverage") != expected_types:
            failures.append("Node.js evidence type coverage drift")
        if evidence.get("input_domain") != "nodejs-es2022-esm-safe-integer-finite-v1":
            failures.append("Node.js evidence input domain drift")
        if certification.get("certification_decision") != "NOT_CERTIFIED":
            failures.append("Node.js route must remain NOT_CERTIFIED")

    if certification_status != status:
        failures.append("route and certification statuses must match")
    if not manifest.get("maintenance_owner"):
        failures.append("maintenance owner is missing")
    if not manifest.get("review_date"):
        failures.append("review date is missing")

    capabilities = support.get("capabilities", [])
    if status in {"limited", "certified"}:
        supported_status = (
            "certified"
            if status == "certified"
            else "conditional"
            if nodejs
            else "supported"
        )
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
        validate_negative_refs(
            failures,
            route,
            evidence,
            replay_specialized=False,
        )

    strict_requested = strict_evidence_requested(certification)
    if strict_requested:
        formal_equivalence, strict_failures = validate_formal_equivalence(
            route,
            manifest,
            certification,
            validate_live_engine_sources=route_key not in CORE_ROUTE_KEYS,
        )
        failures.extend(strict_failures)
        if specialized:
            _validate_specialized_native_runtime_replay(
                route,
                manifest,
                failures,
            )
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
            contract = module_equivalence.get("module_contract")
            if not isinstance(contract, dict):
                failures.append("module whole-file contract is missing")
            else:
                for field in (
                    "exact_profile_symbol_set",
                    "exact_generated_helper_symbol_set",
                    "exact_profile_signature_set",
                ):
                    if contract.get(field) is not True:
                        failures.append(f"module contract {field} is not true")
                if not isinstance(
                    contract.get("whole_file_closure_sha256"), str
                ):
                    failures.append("module whole-file closure digest is missing")
            whole_file = module_equivalence.get("whole_file_closure")
            if not isinstance(whole_file, dict):
                failures.append("module whole-file closure is missing")
            else:
                if whole_file.get("status") != "PASSED":
                    failures.append("module whole-file closure did not pass")
                if whole_file.get("blocked_declarations") != {
                    "source": [],
                    "target": [],
                }:
                    failures.append("module whole-file closure has blocked declarations")
                if whole_file.get("source_user_call_graph") != {
                    "edges": [],
                    "status": "EMPTY_AND_CLOSED",
                }:
                    failures.append("module source call graph is not empty and closed")
                target_graph = whole_file.get("target_call_graph")
                if not isinstance(target_graph, dict) or (
                    target_graph.get("status")
                    != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
                    or target_graph.get("scope")
                    != "profile-functions-to-emitted-callees"
                    or target_graph.get("helper_internal_calls")
                    != {
                        "status": "CONTENT_BOUND_NOT_EDGE_ENUMERATED",
                        "binding": (
                            "verified_generated_helpers-exact-bytes-and-digests"
                        ),
                    }
                ):
                    failures.append("module target call graph closure is invalid")
                for field in (
                    "verified_language_prelude",
                    "verified_language_wrapper",
                ):
                    boundary = whole_file.get(field)
                    if (
                        not isinstance(boundary, dict)
                        or set(boundary) != {"source", "target"}
                        or contract.get(field) != boundary
                    ):
                        failures.append(
                            f"module {field} is missing or detached from module contract"
                        )
                independence = (
                    contract.get("independence")
                    if isinstance(contract, dict)
                    else None
                )
                if not isinstance(independence, dict) or independence.get(
                    "target_call_graph"
                ) != target_graph:
                    failures.append(
                        "module target call graph is detached from module contract"
                    )
                composition = module_equivalence.get("composition")
                if not isinstance(composition, dict) or (
                    composition.get(
                        "target_profile_to_emitted_call_graph_status"
                    )
                    != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
                    or composition.get(
                        "target_profile_to_emitted_call_graph_scope"
                    )
                    != "profile-functions-to-emitted-callees"
                ):
                    failures.append("module target profile call graph claim drift")

    if module_route and formal_equivalence is not None and module_equivalence is not None:
        formal_receipts = [
            item
            for item in formal_equivalence.get("artifact_refs", [])
            if isinstance(item, dict)
            and item.get("role") == "swift-analyzer-build-receipt"
        ]
        module_receipts = [
            item
            for item in module_equivalence.get("artifact_refs", [])
            if isinstance(item, dict)
            and item.get("role") == "swift-analyzer-build-receipt"
        ]
        swift_required = "swift" in {
            manifest.get("source", {}).get("language"),
            manifest.get("target", {}).get("language"),
        }
        if swift_required:
            if len(formal_receipts) != 1 or len(module_receipts) != 1:
                failures.append(
                    "Swift route must bind exactly one shared analyzer build receipt in function and module evidence"
                )
            elif (
                formal_receipts[0].get("path") != SWIFT_ANALYZER_RECEIPT_PATH
                or {
                    key: formal_receipts[0].get(key)
                    for key in ("path", "sha256", "bytes")
                }
                != {
                    key: module_receipts[0].get(key)
                    for key in ("path", "sha256", "bytes")
                }
            ):
                failures.append(
                    "Swift function/module analyzer build receipt binding differs"
                )
        elif formal_receipts or module_receipts:
            failures.append("non-Swift module route cannot bind a Swift analyzer receipt")

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
        print(f"GATE WALL: {time.monotonic() - started:.3f}s", file=sys.stderr)
        return 2
    decision = "NOT_CERTIFIED" if status != "certified" else "CERTIFIED"
    print(
        f"GATE PASS: {manifest.get('route_key')} status={status} "
        f"decision={decision} wall_seconds={time.monotonic() - started:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
