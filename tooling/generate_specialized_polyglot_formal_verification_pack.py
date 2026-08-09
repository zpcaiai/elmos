#!/usr/bin/env python3
"""Build the exact eight-route C++/Objective-C/Swift/Java formal pack.

This generator deliberately consumes only already executed, byte-bound Batch 29
route evidence.  It does not infer a four-language complete matrix, does not
touch the legacy exact-30 pack, and cannot promote local assumption-bound proof
to certification.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import generate_polyglot_formal_verification_pack as base


ROOT = Path(__file__).resolve().parents[1]
PACK_KEY = "polyglot-specialized-8-route-formal-equivalence-v1"
SEMANTIC_PROFILE = "typed-pure-function-v1"
MODULE_PROFILE = "typed-pure-module-v1"
INPUT_DOMAIN = "canonical-finite-no-error-input-domain"
LANGUAGES = ("cpp", "objc", "swift", "java")
EXACT_ROUTE_KEYS = (
    "cpp-to-objc",
    "objc-to-cpp",
    "cpp-to-swift",
    "swift-to-cpp",
    "objc-to-swift",
    "swift-to-objc",
    "cpp-to-java",
    "java-to-cpp",
)
SWIFT_DEPENDENCY_TREE = {
    "identity": "swift-syntax",
    "version": "600.0.1",
    "revision": "0687f71944021d616d34d922343dcef086855920",
    "sha256": "sha256:b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d",
    "file_count": 753,
    "bytes": 8_866_479,
}
SWIFT_DEPENDENCY_SEED = "verified-content-addressed-cache"
SWIFT_DEPENDENCY_CACHE_KEY = (
    "swift-syntax-600.0.1-0687f71944021d616d34d922343dcef086855920-"
    "b78ec1b227a6cbe43ca239585f66907e50485b9119f96b5461bfc888f0e5f45d"
)
SWIFT_CACHE_KEYS = {
    "cache_key",
    "cache_schema",
    "identity",
    "version",
    "revision",
    "seed",
    "sha256",
    "file_count",
    "bytes",
}
SWIFT_MIRROR_KEYS = {
    "seed",
    "cache",
    "git",
    "identity",
    "version",
    "revision",
    "sha256",
    "file_count",
    "bytes",
}
SWIFT_GIT_IDENTITY = {
    "path": "/Applications/Xcode.app/Contents/Developer/usr/bin/git",
    "sha256": "sha256:10f9c1df894525ae4c7454258febab6d3d25071062b42cb48dbb1842cdffd2a9",
    "version": "git version 2.50.1 (Apple Git-155)",
}
BLOCKS = (
    "signature-types-and-names",
    "typed-literals",
    "integer-arithmetic-safe-domain",
    "finite-number-transport-and-comparison",
    "boolean-short-circuit-and-branch",
    "if-else-path-conditions",
    "return-and-totality",
    "concrete-source-spans",
    "module-composition",
    "string-semantics",
    "finite-number-arithmetic",
    "out-of-domain-arithmetic-errors",
)
LOCALLY_EXERCISED_BLOCKS = frozenset(BLOCKS[:9])
PACKED_REPLAY_COMMAND = [
    "uv",
    "--project",
    "certification/formal-artifacts/engine-sources/engines/polyglot-route-engine",
    "run",
    "--locked",
    "python",
    "certification/replay/validate_packed_route.py",
    "--route",
    ".",
]
PACKED_REPLAY_FILES = {
    **base.PACKED_REPLAY_FILES,
    "certification/replay/schemas/batch29/module-equivalence-evidence.schema.json": (
        "schemas/batch29/module-equivalence-evidence.schema.json",
        "replay-schema",
        "module_schema",
    ),
    "certification/replay/schemas/batch29/module-case-manifest.schema.json": (
        "schemas/batch29/module-case-manifest.schema.json",
        "replay-schema",
        "module_case_schema",
    ),
}


def configure_base(repo_root: Path) -> None:
    """Configure the shared immutable-pack helpers for this explicit route set."""

    global ROOT
    ROOT = repo_root.resolve()
    base.ROOT = ROOT
    base.PACK_KEY = PACK_KEY
    base.LANGUAGES = LANGUAGES
    base.BLOCKS = BLOCKS
    base.LOCALLY_EXERCISED_BLOCKS = LOCALLY_EXERCISED_BLOCKS
    base.PACKED_REPLAY_COMMAND = PACKED_REPLAY_COMMAND
    base.PACKED_REPLAY_FILES = PACKED_REPLAY_FILES


def exact_routes() -> list[tuple[str, str, str]]:
    routes: list[tuple[str, str, str]] = []
    for route_key in EXACT_ROUTE_KEYS:
        source, target = route_key.split("-to-", 1)
        routes.append((route_key, source, target))
    return routes


def validate_portable_swift_receipt(route: Path, reference: dict[str, Any]) -> None:
    """Recheck the complete receipt boundary before packaging it."""

    relative = reference.get("path")
    if relative != "certification/formal-artifacts/swift-analyzer-build-receipt.json":
        raise RuntimeError(f"SWIFT_ANALYZER_RECEIPT_PATH_INVALID:{route.name}")
    receipt_path = route / relative
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    validator_directory = ROOT / "scripts" / "batch29"
    validator_directory_value = str(validator_directory)
    if validator_directory_value not in sys.path:
        sys.path.insert(0, validator_directory_value)
    from validate_route import _validate_swift_analyzer_receipt_document

    failures: list[str] = []
    validated = _validate_swift_analyzer_receipt_document(
        receipt,
        label=f"{route.name} Swift analyzer build receipt",
        failures=failures,
    )
    if validated is None or failures:
        detail = " | ".join(failures) if failures else "unknown receipt failure"
        raise RuntimeError(f"SWIFT_ANALYZER_RECEIPT_INVALID:{route.name}:{detail}")


def validate_source_routes(repo_root: Path) -> None:
    validator = repo_root / "scripts" / "batch29" / "validate_route.py"
    if not validator.is_file():
        raise RuntimeError(f"BATCH29_VALIDATOR_MISSING:{validator}")
    for route_key, _, _ in exact_routes():
        completed = subprocess.run(
            [sys.executable, str(validator), str(repo_root / "routes" / route_key)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"BATCH29_ROUTE_INVALID:{route_key}:{detail}")


def copy_module_closure(
    route: Path,
    target_root: Path,
    certification: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    module_ref = certification.get("module_equivalence")
    if not isinstance(module_ref, dict):
        raise RuntimeError(f"MODULE_EQUIVALENCE_REQUIRED:{route.name}")
    module_relative = module_ref.get("path")
    if module_relative != "certification/module-equivalence.json":
        raise RuntimeError(f"MODULE_REFERENCE_INVALID:{route.name}")
    module_path = base.route_relative_file(
        route, module_relative, label=f"{route.name}_MODULE_WRAPPER"
    )
    if (
        base.digest_file(module_path) != module_ref.get("sha256")
        or module_path.stat().st_size != module_ref.get("bytes")
    ):
        raise RuntimeError(f"MODULE_REFERENCE_TAMPERED:{route.name}")
    module = base.load_json(module_path)
    if (
        module.get("profile") != MODULE_PROFILE
        or module.get("local_verification_status") != "PASSED"
        or module.get("status") != "PASSED"
        or module.get("certification_status") != "NOT_CERTIFIED"
        or module.get("external_verification_status") != "NOT_RUN"
    ):
        raise RuntimeError(f"MODULE_STATUS_BOUNDARY_INVALID:{route.name}")
    contract = module.get("module_contract")
    independence = contract.get("independence") if isinstance(contract, dict) else None
    composition = module.get("composition")
    module_input = module.get("module_input")
    whole_file_closure = module.get("whole_file_closure")
    if (
        not isinstance(contract, dict)
        or contract.get("exact_profile_symbol_set") is not True
        or contract.get("exact_generated_helper_symbol_set") is not True
        or contract.get("exact_profile_signature_set") is not True
        or not isinstance(contract.get("whole_file_closure_sha256"), str)
        or not isinstance(independence, dict)
        or not isinstance(whole_file_closure, dict)
        or contract.get("verified_language_prelude")
        != whole_file_closure.get("verified_language_prelude")
        or contract.get("verified_language_wrapper")
        != whole_file_closure.get("verified_language_wrapper")
        or independence.get("source_user_call_graph_closure")
        != "EMPTY_AND_CLOSED"
        or independence.get("source_user_call_graph_edges") != []
        or independence.get("target_call_graph_policy")
        != "UNSUPPORTED_EXCEPT_EXACT_EMITTER_HELPERS"
        or independence.get("target_call_graph")
        != whole_file_closure.get("target_call_graph")
        or independence.get("shared_state") != "ABSENT_BY_IR_CONSTRUCTION"
        or not isinstance(composition, dict)
        or composition.get("input_domain") != INPUT_DOMAIN
        or composition.get("target_profile_to_emitted_call_graph_status")
        != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
        or composition.get("target_profile_to_emitted_call_graph_scope")
        != "profile-functions-to-emitted-callees"
        or not isinstance(module_input, dict)
        or module_input.get("input_domain") != INPUT_DOMAIN
        or whole_file_closure.get("status") != "PASSED"
        or whole_file_closure.get("blocked_declarations")
        != {"source": [], "target": []}
        or whole_file_closure.get("source_user_call_graph")
        != {"edges": [], "status": "EMPTY_AND_CLOSED"}
        or whole_file_closure.get("target_call_graph", {}).get("status")
        != "EXACT_EMITTER_HELPERS_AND_PINNED_BUILTINS"
    ):
        raise RuntimeError(f"MODULE_CONTRACT_INVALID:{route.name}")
    functions = module.get("functions")
    if not isinstance(functions, list) or len(functions) < 5:
        raise RuntimeError(f"MODULE_FUNCTION_COVERAGE_INVALID:{route.name}")
    covered_types: set[str] = set()
    for function in functions:
        if not isinstance(function, dict):
            raise RuntimeError(f"MODULE_FUNCTION_INVALID:{route.name}")
        signature = function.get("signature")
        if not isinstance(signature, dict):
            raise RuntimeError(f"MODULE_SIGNATURE_INVALID:{route.name}")
        for parameter in signature.get("parameters", []):
            if isinstance(parameter, dict) and isinstance(parameter.get("type"), str):
                covered_types.add(parameter["type"])
        if isinstance(signature.get("return_type"), str):
            covered_types.add(signature["return_type"])
    if not {"integer", "number", "boolean"}.issubset(covered_types):
        raise RuntimeError(f"MODULE_TYPE_COVERAGE_INVALID:{route.name}")

    relative_paths = {module_relative}
    artifact_refs = module.get("artifact_refs")
    if not isinstance(artifact_refs, list) or not artifact_refs:
        raise RuntimeError(f"MODULE_ARTIFACT_REFS_REQUIRED:{route.name}")
    for index, artifact_ref in enumerate(artifact_refs):
        if not isinstance(artifact_ref, dict):
            raise RuntimeError(f"MODULE_ARTIFACT_REF_INVALID:{route.name}:{index}")
        source = base.route_relative_file(
            route,
            artifact_ref.get("path"),
            label=f"{route.name}_MODULE_ARTIFACT_{index}",
        )
        if (
            base.digest_file(source) != artifact_ref.get("sha256")
            or source.stat().st_size != artifact_ref.get("bytes")
        ):
            raise RuntimeError(
                f"MODULE_ARTIFACT_REF_TAMPERED:{route.name}:{artifact_ref.get('path')}"
            )
        relative_paths.add(artifact_ref["path"])
    for relative in sorted(relative_paths):
        source = base.route_relative_file(
            route, relative, label=f"{route.name}_MODULE_BUNDLE_MEMBER"
        )
        base.copy_file(source, target_root / relative)
    return module, module_relative


def collect_route_evidence(
    pack: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    routes: list[dict[str, Any]] = []
    copies: list[dict[str, Any]] = []
    for route_key, source, target in exact_routes():
        route = ROOT / "routes" / route_key
        manifest = base.load_json(route / "route.json")
        certification = base.load_json(
            route / "certification" / "certification.json"
        )
        if (
            manifest.get("route_key") != route_key
            or manifest.get("source", {}).get("language") != source
            or manifest.get("target", {}).get("language") != target
        ):
            raise RuntimeError(f"ROUTE_IDENTITY_MISMATCH:{route_key}")
        if manifest.get("profiles", {}).get("semantic_profile") != SEMANTIC_PROFILE:
            raise RuntimeError(f"SEMANTIC_PROFILE_MISMATCH:{route_key}")
        if manifest.get("gates", {}).get(
            "canonical_finite_no_error_input_domain_required"
        ) is not True:
            raise RuntimeError(f"SPECIALIZED_DOMAIN_GATE_MISSING:{route_key}")
        if (
            certification.get("status") != "limited"
            or certification.get("certification_decision") != "NOT_CERTIFIED"
            or certification.get("declared_scope")
            != f"{SEMANTIC_PROFILE}+{MODULE_PROFILE}"
        ):
            raise RuntimeError(f"ROUTE_STATUS_BOUNDARY_INVALID:{route_key}")
        target_root = pack / "evidence" / "routes" / route_key
        formal, formal_relative, replay_members = base.copy_route_formal_bundle(
            route, target_root, certification
        )
        module, module_relative = copy_module_closure(
            route, target_root, certification
        )
        formal_receipts = [
            item
            for item in formal.get("artifact_refs", [])
            if isinstance(item, dict)
            and item.get("role") == "swift-analyzer-build-receipt"
        ]
        module_receipts = [
            item
            for item in module.get("artifact_refs", [])
            if isinstance(item, dict)
            and item.get("role") == "swift-analyzer-build-receipt"
        ]
        if "swift" in {source, target}:
            if len(formal_receipts) != 1 or len(module_receipts) != 1:
                raise RuntimeError(
                    f"SWIFT_ANALYZER_BUILD_RECEIPT_COUNT_INVALID:{route_key}"
                )
            if (
                formal_receipts[0].get("path")
                != "certification/formal-artifacts/swift-analyzer-build-receipt.json"
                or {
                    key: formal_receipts[0].get(key)
                    for key in ("path", "sha256", "bytes")
                }
                != {
                    key: module_receipts[0].get(key)
                    for key in ("path", "sha256", "bytes")
                }
            ):
                raise RuntimeError(
                    f"SWIFT_ANALYZER_BUILD_RECEIPT_BINDING_INVALID:{route_key}"
                )
            validate_portable_swift_receipt(route, formal_receipts[0])
        elif formal_receipts or module_receipts:
            raise RuntimeError(
                f"SWIFT_ANALYZER_BUILD_RECEIPT_UNEXPECTED:{route_key}"
            )
        proof_status = formal.get("formal_proof", {}).get("status")
        if proof_status != "PROVED_UNDER_ASSUMPTIONS":
            raise RuntimeError(
                f"ROUTE_FORMAL_PROOF_NONPASSING:{route_key}:{proof_status}"
            )
        evidence_id = f"route-evidence-{route_key}"
        module_evidence_id = f"route-module-evidence-{route_key}"
        copies.append(
            {
                "evidence_id": evidence_id,
                "relative": (
                    target_root / formal_relative
                ).relative_to(pack).as_posix(),
                "module_evidence_id": module_evidence_id,
                "module_relative": (
                    target_root / module_relative
                ).relative_to(pack).as_posix(),
                "source_ir_sha256": formal["semantic_ir"]["source_ir_sha256"],
                "target_ir_sha256": formal["semantic_ir"][
                    "target_relift_ir_sha256"
                ],
                "environment_sha256": formal["environment_sha256"],
                "artifact_sha256": formal["artifact_sha256"],
                "behavior_cases": formal["behavior_equivalence"]["total_cases"],
                "module_function_count": len(module["functions"]),
                "proof_status": proof_status,
                "replay_members": replay_members,
            }
        )
        routes.append(
            {
                "route_key": route_key,
                "source_language": source,
                "target_language": target,
                "route_version": str(manifest.get("version")),
                "semantic_profile": SEMANTIC_PROFILE,
                "composition_id": f"composition-{route_key}",
                "artifact_evidence_ids": [evidence_id],
                "module_evidence_id": module_evidence_id,
                "packed_replay_evidence_ids": [
                    base.packed_replay_evidence_id(route_key, member["member"])
                    for member in replay_members
                ],
            }
        )
    if tuple(route["route_key"] for route in routes) != EXACT_ROUTE_KEYS:
        raise RuntimeError("SPECIALIZED_ROUTE_SET_IS_NOT_EXACT")
    return routes, copies


def build_campaign(
    pack: Path,
    routes: list[dict[str, Any]],
    route_copies: list[dict[str, Any]],
    bundle_paths: dict[str, str],
) -> dict[str, Any]:
    campaign = base.build_campaign(pack, routes, route_copies, bundle_paths)
    campaign["schema_version"] = 2
    campaign["route_policy"] = "exact-explicit-set"
    campaign["required_route_keys"] = list(EXACT_ROUTE_KEYS)
    campaign["input_domain"] = INPUT_DOMAIN
    campaign["limitations"] = [
        "The route inventory is the explicit specialized eight; it is not a four-language complete matrix and does not imply 12 or 72 directions.",
        "Packed replay independently revalidates the byte-bound function and five-function module closure but does not regenerate native evidence.",
        "Integer arithmetic is limited to the canonical finite no-error domain; arithmetic-error behavior outside that domain is blocked.",
        "Finite number support is transport/comparison only; number arithmetic, non-finite values, and string semantics are unsupported.",
        "All local formal results are PROVED_UNDER_ASSUMPTIONS; analyzer, compiler, runtime, and external soundness remain NOT_RUN.",
        "Independent verification, customer workloads, production execution, and external certification remain NOT_RUN.",
    ]

    copy_by_route = {
        item["evidence_id"].removeprefix("route-evidence-"): item
        for item in route_copies
    }
    for route_key in EXACT_ROUTE_KEYS:
        item = copy_by_route[route_key]
        base.add_evidence(
            pack,
            campaign,
            item["module_evidence_id"],
            item["module_relative"],
            role="route-module-evidence",
        )

    routes_by_key = {route["route_key"]: route for route in routes}
    for obligation in campaign["obligations"]:
        block = obligation.get("semantic_block")
        if block != "module-composition":
            continue
        evidence_ids = obligation["evidence_ids"]
        if obligation.get("kind") == "route-behavior":
            evidence_ids.append(
                copy_by_route[obligation["route_key"]]["module_evidence_id"]
            )
        elif obligation.get("kind") == "source-lifting":
            language = obligation["source_language"]
            evidence_ids.extend(
                copy_by_route[route_key]["module_evidence_id"]
                for route_key, route in routes_by_key.items()
                if route["source_language"] == language
            )
        elif obligation.get("kind") == "target-lowering":
            language = obligation["target_language"]
            evidence_ids.extend(
                copy_by_route[route_key]["module_evidence_id"]
                for route_key, route in routes_by_key.items()
                if route["target_language"] == language
            )
        obligation["evidence_ids"] = list(dict.fromkeys(evidence_ids))
    base.write_json(pack / "formal-route-campaign.json", campaign)
    return campaign


def specialize_base_files(pack: Path) -> None:
    manifest = base.load_json(pack / "pack.json")
    manifest["status"] = "limited"
    manifest["scope"].update(
        {
            "migration_route": "cpp-objc-swift-java-exact-explicit-8-routes",
            "route_count": 8,
            "route_policy": "exact-explicit-set",
            "input_domain": INPUT_DOMAIN,
            "supported_types": ["integer", "finite-number", "boolean"],
            "blocked_semantics": [
                "string",
                "number-arithmetic",
                "non-finite-number",
                "arithmetic-error-domain",
            ],
        }
    )
    manifest["tags"] = [
        "formal-equivalence",
        "polyglot",
        "specialized-exact-8-directed-routes",
        "typed-pure-module",
        "not-certified",
    ]
    base.write_json(pack / "pack.json", manifest)

    support = base.load_json(pack / "support-matrix.json")
    support["capabilities"][0].update(
        {
            "status": "conditional",
            "limitations": [
                "Exact explicit eight directions only; unsupported pairs fail closed.",
                "Integer behavior is conditional on the canonical finite no-error input domain.",
                "Finite numbers are transport/comparison only; boolean logic and branches are covered.",
                "String and finite-number arithmetic semantics are blocked.",
                "Local theorem-under-assumptions evidence is not certification.",
            ],
        }
    )
    support["capabilities"][1].update(
        {
            "key": "specialized-integer-safe-domain-and-finite-number-transport",
            "status": "conditional",
            "limitations": [
                "The copied aggregate arithmetic campaign is residual background evidence, not a proof of out-of-domain runtime behavior.",
                "Overflow, division by zero, non-finite values, and number arithmetic remain blocked.",
            ],
        }
    )
    support["capabilities"][2]["limitations"] = [
        "Strings, number arithmetic, out-of-domain arithmetic errors, mutable state, calls, exceptions, I/O, concurrency, frameworks, and databases are outside scope."
    ]
    base.write_json(pack / "support-matrix.json", support)

    property_spec = base.load_json(pack / "properties" / "sample.json")
    property_spec["generator"]["constraints"] = [
        f"profile={SEMANTIC_PROFILE}",
        "route-set=exact-specialized-8",
        f"input-domain={INPUT_DOMAIN}",
    ]
    base.write_json(pack / "properties" / "sample.json", property_spec)

    model = base.load_json(pack / "models" / "model.json")
    model["invariants"] = [
        item.replace("route-set-is-exactly-thirty", "route-set-is-exact-specialized-eight")
        for item in model["invariants"]
    ]
    base.write_json(pack / "models" / "model.json", model)

    assurance = base.load_json(pack / "assurance" / "assurance-case.json")
    assurance["top_claim"] = (
        "The explicit specialized eight-route typed function and module campaign "
        "has replayable local evidence and fails closed on every unresolved boundary."
    )
    base.write_json(pack / "assurance" / "assurance-case.json", assurance)

    for relative in (
        "certification/evidence.json",
        "certification/certification.json",
    ):
        document = base.load_json(pack / relative)
        document["metrics"]["directed_route_count"] = 8
        if relative.endswith("certification.json"):
            document["status"] = "limited"
            document["exact_scope"] = manifest["scope"]
            document["limitations"] = [
                "NOT_CERTIFIED",
                "Exact explicit specialized eight routes only.",
                "Formal route compositions contain required NOT_RUN source/target soundness obligations.",
                "String, number arithmetic, non-finite number, and arithmetic-error domains are blocked.",
                "Independent verification and external/customer/production validation are NOT_RUN.",
            ]
        base.write_json(pack / relative, document)


def write_corpus_manifests(pack: Path, *, route_set_digest: str) -> None:
    values = {
        "development": (
            "local-development-integer",
            "Each exact route executes an independent integer function corpus within the safe domain.",
        ),
        "negative": (
            "local-specialized-negative",
            "Each applicable analyzer rejection, string/number-domain control, overflow preflight, helper tamper, undeclared pair, and missing symbol is recorded with a stable reason code.",
        ),
        "holdout": (
            "local-separated-finite-number-holdout",
            "Each exact route transports finite numbers including signed zero and finite boundaries; external independence remains NOT_RUN.",
        ),
        "representative-workloads": (
            "bounded-boolean-branch-workload",
            "Each exact route executes nested short-circuit boolean logic with true/false literals and a branch; customer representativeness remains NOT_RUN.",
        ),
    }
    for key, (dataset_class, note) in values.items():
        base.write_json(
            pack / "corpus" / key / "manifest.json",
            {
                "schema_version": 1,
                "corpus": key,
                "status": "passed",
                "source_digest": route_set_digest,
                "dataset_digest": base.aggregate_digest(
                    {
                        "corpus": key,
                        "route_set": route_set_digest,
                        "input_domain": INPUT_DOMAIN,
                    }
                ),
                "evidence_refs": ["evidence/route-set.json"],
                "dataset_class": dataset_class,
                "notes": [note],
            },
        )


def write_readme(pack: Path) -> None:
    (pack / "README.md").write_text(
        "# Specialized polyglot exact-8 formal equivalence v1\n\n"
        "Batch 35 aggregate for exactly eight directed routes: C++↔Objective-C, "
        "C++↔Swift, Objective-C↔Swift, and C++↔Java. This is an explicit set, not "
        "a four-language 12-route matrix and not a nine-language 72-route matrix.\n\n"
        f"The local profile is `{SEMANTIC_PROFILE}+{MODULE_PROFILE}` over "
        f"`{INPUT_DOMAIN}`. Integer behavior is safe-domain conditional; finite "
        "numbers are transport/comparison only; boolean logic and branching are "
        "covered. Strings, number arithmetic, non-finite values, and arithmetic "
        "error behavior are blocked.\n\n"
        "Every packed route includes the three independent function corpora, "
        "five-function module composition, function/module formal input-SMT-result "
        "closures, frozen validator/schema sources, and content-addressed replay. "
        "Native regeneration, compiler/runtime soundness, independent review, "
        "customer evidence, production execution, and external certification remain "
        "`NOT_RUN`; the pack remains `limited / NOT_CERTIFIED`.\n",
        encoding="utf-8",
    )
    (pack / "certification" / "gap-inventory.md").write_text(
        "# Remaining formal and certification gaps\n\n"
        "- Independently prove or validate source and target analyzer/emitter soundness.\n"
        "- Add an external verifier and independently controlled route regeneration.\n"
        "- Define and evidence Unicode/string semantics before enabling strings.\n"
        "- Define finite-number arithmetic rounding, payload, and exceptional-result semantics before enabling number arithmetic.\n"
        "- Model language-specific overflow, undefined behavior, traps, and division errors outside the canonical finite no-error domain.\n"
        "- Execute representative customer repositories and production-equivalent security/performance campaigns.\n"
        "- Obtain external certification; current certification state is NOT_CERTIFIED.\n",
        encoding="utf-8",
    )


def build_staged_pack(pack: Path, arithmetic_campaign: Path) -> tuple[int, int]:
    base.prepare_directories(pack)
    routes, route_copies = collect_route_evidence(pack)
    base.copy_file(arithmetic_campaign, pack / "solver" / "arithmetic-campaign.json")
    arithmetic = base.load_json(pack / "solver" / "arithmetic-campaign.json")
    if arithmetic.get("solver", {}).get("version") != "4.16.0":
        raise RuntimeError("ARITHMETIC_SOLVER_VERSION_NOT_LOCKED")
    if arithmetic.get("all_required_proved") is not False:
        raise RuntimeError("ARITHMETIC_CAMPAIGN_MUST_PRESERVE_RESIDUAL_STATUS")
    bundle_paths = base.write_bundle_evidence(pack, route_copies)
    campaign = build_campaign(pack, routes, route_copies, bundle_paths)
    base.base_pack_files(
        pack,
        source_digest=base.digest_file(pack / bundle_paths["source"]),
        target_digest=base.digest_file(pack / bundle_paths["target"]),
        environment_digest=base.digest_file(pack / bundle_paths["environment"]),
        arithmetic_digest=base.digest_file(
            pack / "solver" / "arithmetic-campaign.json"
        ),
        total_behavior_cases=sum(
            int(item["behavior_cases"]) for item in route_copies
        ),
        arithmetic_counts=arithmetic.get("counts", {}),
    )
    specialize_base_files(pack)
    route_set_digest = base.digest_file(pack / "evidence" / "route-set.json")
    write_corpus_manifests(pack, route_set_digest=route_set_digest)
    write_readme(pack)
    return len(routes), len(campaign["obligation_matrix"])


def publish_staged_pack(staging: Path, destination: Path) -> None:
    if destination.is_symlink() or (destination.exists() and not destination.is_dir()):
        raise RuntimeError(f"PACK_DESTINATION_INVALID:{destination}")
    backup: Path | None = None
    if destination.exists():
        backup = Path(
            tempfile.mkdtemp(prefix=f".{PACK_KEY}-backup-", dir=destination.parent)
        )
        backup.rmdir()
        os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except Exception:
        if backup is not None and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup is not None:
        shutil.rmtree(backup)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--arithmetic-campaign",
        type=Path,
        required=True,
        help="machine-readable residual campaign from prove_arithmetic_compensation.py",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    arithmetic_campaign = args.arithmetic_campaign.resolve(strict=True)
    configure_base(repo_root)
    validate_source_routes(repo_root)
    pack_parent = repo_root / "verification-packs"
    pack_parent.mkdir(parents=True, exist_ok=True)
    destination = pack_parent / PACK_KEY
    staging = Path(
        tempfile.mkdtemp(prefix=f".{PACK_KEY}-staging-", dir=pack_parent)
    )
    try:
        route_count, matrix_count = build_staged_pack(staging, arithmetic_campaign)
        base.validate_staged_pack(repo_root, staging)
        publish_staged_pack(staging, destination)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    print(
        f"PASS: built {destination} with {route_count} exact routes, "
        f"{matrix_count} route/block rows, decision NOT_CERTIFIED"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
