"""Capability-specific operations for all 55 legacy-web Skills."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analysis import ForensicModel, build_forensic_model
from .canonical import canonical_digest, finite_json, redact_json
from .catalog import PACKAGE_DIRECTORY, validate_artifact_payload
from .contracts import ArtifactEnvelope, CapabilityResult, RuntimeRequest, utc_now
from .governance import (
    GovernanceError,
    benchmark_scorecard,
    bounded_repair,
    certification_bundle,
    compile_cutover_plan,
    evaluate_cutover_runbook,
)
from .snapshot import RepositorySnapshot, capture_repository
from .transformation import (
    TransformationError,
    namespace_change_set,
    validate_generated_files,
    validated_mappings,
)
from .verification import (
    VerificationError,
    correlate_traces,
    evaluate_equivalence,
    evaluate_runtime_workload,
)


@dataclass(frozen=True, slots=True)
class OperationProfile:
    code: str
    artifact_type: str
    state: str
    kind: str
    unavailable: tuple[str, ...] = ()


def _profile(
    code: str,
    artifact_type: str,
    kind: str,
    *,
    state: str = "LOCAL_EXECUTED",
    unavailable: tuple[str, ...] = (),
) -> OperationProfile:
    return OperationProfile(
        code=code,
        artifact_type=artifact_type,
        state=state,
        kind=kind,
        unavailable=unavailable,
    )


PROFILES: dict[str, OperationProfile] = {
    "00-modernization-orchestrator": _profile(
        "RUN_MANIFEST_COMPILED", "run-manifest", "orchestrator"
    ),
    "01-job-contract-and-policy-resolver": _profile(
        "JOB_CONTRACT_RESOLVED", "job-contract", "contract"
    ),
    "02-reproducible-repository-snapshot": _profile(
        "REPOSITORY_SNAPSHOT_CAPTURED", "repository-snapshot", "snapshot"
    ),
    "03-checkpoint-resume-cancel": _profile(
        "CHECKPOINT_POLICY_COMPILED", "execution-checkpoint", "checkpoint"
    ),
    "04-wall-clock-eta-and-cost-model": _profile(
        "WALL_CLOCK_ESTIMATE_COMPILED", "wall-clock-estimate", "eta"
    ),
    "05-tool-authority-and-sandbox": _profile(
        "AUTHORITY_PLAN_COMPILED", "authority-plan", "authority"
    ),
    "10-build-and-module-topology": _profile(
        "BUILD_TOPOLOGY_RECOVERED",
        "build-topology",
        "modules",
        unavailable=("native-maven-build",),
    ),
    "11-framework-and-version-fingerprinting": _profile(
        "FRAMEWORK_INVENTORY_RECOVERED", "framework-inventory", "frameworks"
    ),
    "12-runtime-deployment-topology": _profile(
        "RUNTIME_TOPOLOGY_RECOVERED",
        "runtime-topology",
        "runtime",
        unavailable=("running-container",),
    ),
    "13-route-ownership-and-conflict-analysis": _profile(
        "EFFECTIVE_ROUTE_TABLE_RECOVERED", "route-table", "routes"
    ),
    "14-environment-config-overlay-analysis": _profile(
        "CONFIG_OVERLAYS_RECOVERED", "config-overlay", "config"
    ),
    "15-dependency-compatibility-and-jakarta-readiness": _profile(
        "JAKARTA_READINESS_SCORED", "dependency-compatibility", "dependencies"
    ),
    "20-struts1-lifecycle-recovery": _profile(
        "STRUTS1_PIPELINES_RECOVERED", "struts1-pipeline", "recovery"
    ),
    "21-struts2-interceptor-pipeline-recovery": _profile(
        "STRUTS2_PIPELINES_RECOVERED", "struts2-pipeline", "recovery"
    ),
    "22-servlet-container-semantics-recovery": _profile(
        "SERVLET_SEMANTICS_RECOVERED", "servlet-container-ir", "recovery"
    ),
    "23-jsp-taglib-and-view-semantics": _profile(
        "VIEW_SEMANTICS_RECOVERED", "view-semantics", "recovery"
    ),
    "24-request-binding-and-type-conversion": _profile(
        "BINDING_CONVERSION_RECOVERED", "binding-conversion-ir", "recovery"
    ),
    "25-navigation-dispatch-and-error-semantics": _profile(
        "NAVIGATION_SEMANTICS_RECOVERED", "navigation-dispatch-ir", "recovery"
    ),
    "26-session-state-and-scope-semantics": _profile(
        "STATE_SCOPE_RECOVERED", "state-scope-ir", "recovery"
    ),
    "27-security-authn-authz-csrf-semantics": _profile(
        "SECURITY_SEMANTICS_RECOVERED", "security-semantics-ir", "recovery"
    ),
    "28-transaction-and-side-effect-topology": _profile(
        "EFFECT_TOPOLOGY_RECOVERED", "transaction-effect-ir", "recovery"
    ),
    "29-concurrency-lifecycle-and-threadlocal": _profile(
        "CONCURRENCY_SEMANTICS_RECOVERED", "concurrency-lifecycle-ir", "recovery"
    ),
    "30-repository-evidence-graph": _profile(
        "EVIDENCE_GRAPH_BUILT", "repository-evidence-graph", "graph"
    ),
    "31-legacy-web-semantic-ir": _profile(
        "LEGACY_WEB_IR_BUILT", "legacy-web-semantic-ir", "ir"
    ),
    "32-behavioral-contract-and-sequence-mining": _profile(
        "BEHAVIOR_CONTRACTS_MINED", "behavior-contract", "behavior"
    ),
    "33-unknown-semantics-ledger": _profile(
        "UNKNOWN_LEDGER_BUILT", "unknown-semantics-ledger", "unknowns"
    ),
    "34-semantic-risk-scoring": _profile(
        "SEMANTIC_RISKS_SCORED", "semantic-risk-register", "risk"
    ),
    "40-preserve-first-migration-strategy": _profile(
        "PRESERVE_FIRST_STRATEGY_COMPILED", "migration-strategy", "strategy"
    ),
    "41-springboot4-target-architecture": _profile(
        "SPRINGBOOT4_TARGET_COMPILED", "target-architecture", "target"
    ),
    "42-multi-module-conversion-wave-planner": _profile(
        "CONVERSION_WAVES_COMPILED", "conversion-wave-plan", "waves"
    ),
    "43-compatibility-shim-synthesis": _profile(
        "COMPATIBILITY_SHIMS_COMPILED", "compatibility-shim-plan", "shims"
    ),
    "44-packaging-view-and-container-decision": _profile(
        "PACKAGING_DECISION_COMPILED", "packaging-decision", "packaging"
    ),
    "45-cutover-strangler-and-dual-run-plan": _profile(
        "CUTOVER_STATE_MACHINE_COMPILED",
        "cutover-plan",
        "cutover",
        unavailable=("production-cutover-execution",),
    ),
    "50-deterministic-ast-and-config-rewrite": _profile(
        "DETERMINISTIC_STRUCTURED_REWRITE_COMPILED", "rewrite-change-set", "rewrite"
    ),
    "51-struts1-to-springmvc-generator": _profile(
        "STRUTS1_TARGET_GENERATED",
        "generated-target",
        "generator",
        unavailable=("target-build-execution",),
    ),
    "52-struts2-to-springmvc-generator": _profile(
        "STRUTS2_TARGET_GENERATED",
        "generated-target",
        "generator",
        unavailable=("target-build-execution",),
    ),
    "53-servlet-to-springmvc-generator": _profile(
        "SERVLET_TARGET_GENERATED",
        "generated-target",
        "generator",
        unavailable=("target-build-execution",),
    ),
    "54-jakarta-and-dependency-migration": _profile(
        "JAKARTA_STRUCTURED_REWRITE_COMPILED",
        "jakarta-dependency-change-set",
        "jakarta",
        unavailable=("target-build-execution",),
    ),
    "55-spring-security-validation-transaction-generator": _profile(
        "SECURITY_VALIDATION_TRANSACTION_TARGET_GENERATED",
        "security-validation-target",
        "security-generator",
        unavailable=("security-runtime-execution",),
    ),
    "56-jsp-preserve-or-modernize": _profile(
        "JSP_VIEW_TARGET_GENERATED",
        "jsp-view-decision",
        "jsp",
        unavailable=("browser-view-runtime-execution",),
    ),
    "57-source-map-change-provenance": _profile(
        "SOURCE_MAP_BUILT", "semantic-source-map", "source-map"
    ),
    "58-idempotent-change-set-commit": _profile(
        "CHANGE_SET_STAGING_COMMIT_COMPILED",
        "change-set",
        "change-set",
        unavailable=("customer-git-mutation",),
    ),
    "60-static-semantic-coverage": _profile(
        "STATIC_SEMANTIC_COVERAGE_MEASURED", "static-semantic-coverage", "coverage"
    ),
    "61-test-and-scenario-generation": _profile(
        "SCENARIOS_GENERATED", "scenario-catalog", "scenarios"
    ),
    "62-differential-http-and-view-oracle": _profile(
        "HTTP_VIEW_ORACLE_EVALUATED",
        "equivalence-report",
        "http-oracle",
        unavailable=("legacy-target-runtime-capture",),
    ),
    "63-session-db-and-side-effect-diff": _profile(
        "STATE_EFFECT_ORACLE_EVALUATED",
        "equivalence-report",
        "state-oracle",
        unavailable=("database-cdc-capture",),
    ),
    "64-security-equivalence-and-hardening": _profile(
        "SECURITY_ORACLE_EVALUATED",
        "security-equivalence",
        "security-oracle",
        unavailable=("independent-security-verification",),
    ),
    "65-concurrency-performance-and-fault-verification": _profile(
        "RUNTIME_STRESS_ORACLE_EVALUATED",
        "runtime-verification-plan",
        "runtime-verification",
        unavailable=("runtime-load-fault-capture",),
    ),
    "66-observability-and-trace-correlation": _profile(
        "TRACE_CORRELATION_EVALUATED",
        "trace-correlation",
        "trace",
        unavailable=("distributed-trace-capture",),
    ),
    "70-mismatch-classification": _profile(
        "MISMATCHES_CLASSIFIED", "mismatch-ledger", "mismatch"
    ),
    "71-bounded-semantic-auto-repair": _profile(
        "BOUNDED_REPAIR_CHANGE_SET_GENERATED",
        "repair-change-set",
        "repair",
        unavailable=("automatic-write-to-customer-repository",),
    ),
    "72-impact-based-regression-selection": _profile(
        "IMPACT_REGRESSION_SELECTED", "regression-selection", "regression"
    ),
    "73-production-cutover-rollback": _profile(
        "CUTOVER_ROLLBACK_STATE_EVALUATED",
        "cutover-runbook",
        "cutover-runbook",
        unavailable=("production-adapter-execution",),
    ),
    "74-evidence-bundle-and-e0-e5-certification": _profile(
        "LOCAL_E0_E4_AND_EXTERNAL_GATE_EVALUATED",
        "certification-bundle",
        "certification",
        unavailable=("independent-verifier", "production-evidence"),
    ),
    "75-golden-route-benchmark-and-learning-cache": _profile(
        "GOLDEN_ROUTE_SCORECARD_EVALUATED",
        "golden-route-scorecard",
        "benchmark",
        unavailable=("independent-customer-learning-verification",),
    ),
}


def _snapshot(request: RuntimeRequest) -> RepositorySnapshot | None:
    root = request.inputs.get("repository_root")
    if not isinstance(root, str) or not root:
        return None
    try:
        # Do not cache by directory mtime: editing a file does not reliably
        # update its parent directory, which could return stale migration IR.
        return capture_repository(root)
    except OSError:
        return None


def _model(
    request: RuntimeRequest,
) -> tuple[RepositorySnapshot | None, ForensicModel | None]:
    snapshot = _snapshot(request)
    return snapshot, build_forensic_model(snapshot) if snapshot is not None else None


def _artifact(
    request: RuntimeRequest,
    profile: OperationProfile,
    payload: Mapping[str, Any],
    *,
    evidence_refs: tuple[str, ...] = (),
    confidence: float = 0.75,
    input_hashes: tuple[str, ...] = (),
) -> ArtifactEnvelope:
    package_root = Path(__file__).resolve().parents[4] / "skills" / PACKAGE_DIRECTORY
    safe_payload = redact_json(dict(payload))
    validate_artifact_payload(package_root, profile.artifact_type, safe_payload)
    return ArtifactEnvelope(
        artifact_type=profile.artifact_type,
        payload=safe_payload,
        producer_skill=request.skill_id,
        input_hashes=input_hashes,
        policy_snapshot_hash=canonical_digest(request.policy),
        environment_id=request.authority.environment_id,
        evidence_refs=evidence_refs,
        confidence=confidence,
    )


def _blocked(
    request: RuntimeRequest, profile: OperationProfile, reason: str
) -> CapabilityResult:
    artifact = _artifact(
        request,
        profile,
        {"status": "BLOCKED", "reason": reason, "externalEvidence": "NOT_RUN"},
        confidence=0.0,
    )
    return CapabilityResult(
        skill_id=request.skill_id,
        handler_id="legacy-web:" + request.skill_id,
        state="BLOCKED",
        code="BLOCKED_MISSING_AUTHORITY_OR_INPUT",
        artifacts=(artifact,),
        warnings=(reason,),
        unavailable=profile.unavailable,
    )


def _orchestrator(
    request: RuntimeRequest, profile: OperationProfile
) -> CapabilityResult:
    target = request.inputs.get(
        "target", {"framework": "spring-boot", "versionLine": "4.x", "java": 21}
    )
    manifest = {
        "apiVersion": "elmos.dev/v1",
        "kind": "RepositoryModernizationJob",
        "jobId": request.job_id,
        "tenantId": request.tenant_id,
        "state": "CREATED",
        "phaseDag": [
            "SNAPSHOTTING",
            "FORENSICS",
            "SEMANTIC_RECOVERY",
            "IR_BUILT",
            "PLANNED",
            "TRANSFORMING",
            "BUILDING",
            "VERIFYING",
            "REPAIRING",
            "E4_VERIFIED",
            "CUTOVER_READY",
            "E5_CERTIFIED",
        ],
        "target": target,
        "authority": {
            "environmentId": request.authority.environment_id,
            "profile": request.authority.profile,
            "approved": request.authority.approved,
        },
        "externalEvidence": "NOT_RUN",
        "certification": "NOT_CERTIFIED",
    }
    return _success(request, profile, manifest, confidence=0.95)


def _contract(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    target = request.inputs.get(
        "target", {"framework": "spring-boot", "versionLine": "4.x", "java": 21}
    )
    if not isinstance(target, Mapping) or target.get("framework") != "spring-boot":
        return _blocked(request, profile, "target.framework must be spring-boot")
    policy = {
        "mode": request.inputs.get("mode", "preserve-first"),
        "view": request.inputs.get("view", "preserve"),
        "security": request.inputs.get("security", "preserve"),
        "packaging": request.inputs.get("packaging", "auto"),
        "cutover": "plan-only",
        "equivalence": request.inputs.get("equivalence", "strict"),
        "target": dict(target),
        "resolvedAt": utc_now(),
    }
    return _success(
        request,
        profile,
        {
            "jobContract": {
                "jobId": request.job_id,
                "source": {"repository": "local-snapshot", "credentialsRef": None},
                "target": dict(target),
                "strategy": policy,
            },
            "policySnapshotHash": canonical_digest(policy),
            "externalEffectsAuthorized": False,
        },
        confidence=1.0,
    )


def _checkpoint(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    input_hash = canonical_digest(request.inputs)
    payload = {
        "jobId": request.job_id,
        "stepId": request.skill_id,
        "attemptId": request.request_id,
        "state": "safe-point",
        "inputHash": input_hash,
        "policySnapshotHash": canonical_digest(request.policy),
        "ownerEnvironmentId": request.authority.environment_id,
        "leaseId": request.idempotency_key,
        "fencingToken": request.authority.fencing_token,
        "artifacts": [],
        "sideEffects": [],
        "resumeCursor": {"next": "resume-from-input-hash"},
        "createdAt": utc_now(),
    }
    return _success(request, profile, payload, confidence=1.0)


def _eta(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    snapshot, model = _model(request)
    files = (
        len(snapshot.files)
        if snapshot
        else int(request.inputs.get("file_count", 0) or 0)
    )
    bytes_total = (
        snapshot.total_bytes if snapshot else int(request.inputs.get("bytes", 0) or 0)
    )
    endpoints = (
        len(model.routes)
        if model
        else int(request.inputs.get("endpoint_count", 0) or 0)
    )
    loc = (
        sum((item.text or "").count("\n") + 1 for item in snapshot.files)
        if snapshot
        else int(request.inputs.get("loc", 0) or 0)
    )
    base = max(
        1.0, files * 0.02 + bytes_total / 8_000_000 + endpoints * 0.8 + loc / 10_000
    )
    phases = [
        {"phase": phase, "p50": round(base * multiplier, 3)}
        for phase, multiplier in (
            ("transformation", 1.0),
            ("verification", 1.6),
            ("repair-certification", 0.7),
        )
    ]
    p50 = sum(item["p50"] for item in phases)
    payload = {
        "estimateVersion": "1.0.0",
        "jobId": request.job_id,
        "asOf": utc_now(),
        "unit": "seconds",
        "p50": round(p50, 3),
        "p80": round(p50 * 1.5, 3),
        "p95": round(p50 * 2.0, 3),
        "remainingPhases": phases,
        "confidence": 0.55 if not snapshot else 0.72,
        "features": {
            "loc": loc,
            "files": files,
            "bytes": bytes_total,
            "endpoints": endpoints,
            "cacheHit": 0.0,
        },
        "assumptions": [
            "machine wall-clock only",
            "human approval wait excluded",
            "external provider/runtime evidence unavailable",
        ],
        "humanWaitExcluded": True,
        "model": {"id": "legacy-web-eta-v1", "version": "1.0.0"},
    }
    return _success(request, profile, payload, confidence=payload["confidence"])


def _authority(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    payload = {
        "profile": request.authority.profile,
        "environmentId": request.authority.environment_id,
        "scopes": list(request.authority.scopes),
        "fencingToken": request.authority.fencing_token,
        "approved": request.authority.approved,
        "policy": {
            "filesystem": "repository-read"
            if request.authority.profile == "scan-readonly"
            else "staged-workspace",
            "network": "deny",
            "database": "none",
            "secrets": "none",
        },
        "externalEffectsAllowed": False,
    }
    return _success(request, profile, payload, confidence=1.0)


def _forensic(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(
            request, profile, "repository_root is required for repository forensics"
        )
    values: dict[str, Any] = {
        "modules": list(model.modules),
        "frameworks": list(model.framework_inventory),
        "runtime": model.runtime_topology,
        "routes": list(model.routes),
        "configOverlays": list(model.config_overlays),
        "dependencies": list(model.dependencies),
        "unknowns": list(model.unknowns),
        "snapshotDigest": snapshot.digest,
    }
    selected = {
        "modules": {"modules": values["modules"]},
        "frameworks": {"frameworks": values["frameworks"]},
        "runtime": {"runtime": values["runtime"]},
        "routes": {
            "routes": values["routes"],
            "conflicts": _route_conflicts(model.routes),
        },
        "config": {"overlays": values["configOverlays"]},
        "dependencies": {
            "dependencies": values["dependencies"],
            "jakartaReadiness": _jakarta_readiness(model.dependencies),
        },
    }.get(profile.kind, values)
    return _success(
        request,
        profile,
        selected,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",),
        confidence=0.82,
    )


def _recovery(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(
            request, profile, "repository_root is required for semantic recovery"
        )
    recovery = model.recovery
    if profile.kind == "recovery":
        payload = {
            "snapshotDigest": snapshot.digest,
            "recovered": recovery,
            "frameworks": [item["name"] for item in model.framework_inventory],
            "preservationPolicy": "preserve-first",
            "unknownRefs": [item["id"] for item in model.unknowns],
        }
    else:
        payload = {"snapshotDigest": snapshot.digest, "recovered": recovery}
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",),
        confidence=0.78,
    )


def _model_operation(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(
            request, profile, "repository_root is required for semantic modeling"
        )
    if profile.kind == "graph":
        payload = model.graph
    elif profile.kind == "ir":
        payload = model.ir
    elif profile.kind == "behavior":
        payload = _behavior_contract(model, snapshot)
    elif profile.kind == "unknowns":
        payload = {"ledgerVersion": "1.0.0", "items": list(model.unknowns)}
    else:
        payload = _risk_register(model)
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",),
        confidence=0.76 if model.unknowns else 0.9,
    )


def _plan(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if (
        profile.kind in {"strategy", "target", "waves", "shims", "packaging", "cutover"}
        and model is None
    ):
        return _blocked(
            request,
            profile,
            "repository_root is required to plan a repository migration",
        )
    target = dict(
        request.inputs.get(
            "target",
            {
                "springBoot": "4.x",
                "springFramework": "7.x",
                "jakartaEE": "11",
                "servlet": "6.1",
                "java": 21,
                "packaging": "mixed",
            },
        )
    )
    if profile.kind == "strategy":
        payload = {
            "strategy": "preserve-first",
            "allowedDeltas": [],
            "preserved": [
                "route",
                "session",
                "security",
                "transaction",
                "database",
                "effects",
                "JSP",
            ],
            "deferred": ["JSP-to-React", "domain-refactor", "database-schema-refactor"],
        }
    elif profile.kind == "target":
        payload = {
            "target": target,
            "exactTuple": _is_exact_target(target),
            "maintenanceOwner": request.inputs.get("maintenance_owner", "unassigned"),
            "dependencyLockPolicy": "required",
            "supportedJava": [17, 21, 25],
            "externalEvidence": "NOT_RUN",
        }
    elif profile.kind == "waves":
        payload = _wave_plan(model)
    elif profile.kind == "shims":
        payload = {
            "compatibilityShims": [
                {
                    "id": "shim:legacy-navigation",
                    "purpose": "preserve forward/redirect/include distinction",
                    "removalGate": "all navigation contracts verified",
                },
                {
                    "id": "shim:form-binding",
                    "purpose": "preserve ActionForm reset/populate/validation ordering",
                    "removalGate": "all binding contracts migrated",
                },
            ]
        }
    elif profile.kind == "packaging":
        payload = {
            "decision": "traditional-war"
            if any(module["packaging"] in {"war", "ear"} for module in model.modules)
            else "jar",
            "view": "preserve-jsp",
            "container": "external-container-required-until-proven",
            "reasons": [
                "preserve-first",
                "runtime container semantics are not statically complete",
            ],
        }
    else:
        payload = compile_cutover_plan(
            request,
            route_ids=[str(item["id"]) for item in model.routes],
            snapshot_digest=snapshot.digest if snapshot else "NOT_RUN",
        )
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (),
        confidence=0.72,
    )


def _transform(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(
            request, profile, "repository_root is required for IR-driven transformation"
        )
    if profile.kind in {"rewrite", "jakarta"}:
        try:
            mappings = validated_mappings(
                request.inputs.get("rewrite_mappings")
                if profile.kind == "rewrite"
                else None
            )
        except TransformationError as exc:
            return _blocked(request, profile, str(exc))
        change_set = namespace_change_set(snapshot, jakarta=True, mappings=mappings)
        payload = {
            "mode": "staged-only",
            "changes": change_set["files"],
            "changedFiles": len(change_set["files"]),
            "blockedFiles": change_set["blockedFiles"],
            "operationCount": change_set["operationCount"],
            "sourceSnapshotDigest": snapshot.digest,
            "targetBuild": "NOT_RUN",
            "gitMutation": False,
            "reversible": True,
            "rewriteCore": "syntax-aware-bounded-parsers",
            "failClosed": True,
        }
    elif profile.kind == "generator":
        files = _generate_controllers(model, profile.code)
        files.update(_target_support_files())
        payload = {
            "mode": "staged-only",
            "target": _resolved_target(request),
            "files": files,
            "fileDigests": {
                path: canonical_digest(content) for path, content in files.items()
            },
            "sourceSnapshotDigest": snapshot.digest,
            "targetBuild": "NOT_RUN",
            "gitMutation": False,
            "provenance": _generated_provenance(model, snapshot, files),
        }
    elif profile.kind == "security-generator":
        files = _security_validation_transaction_files(model)
        payload = {
            "files": files,
            "fileDigests": {
                path: canonical_digest(content) for path, content in files.items()
            },
            "allowlistedBindings": [
                binding["sourceName"] for binding in model.ir.get("bindings", [])
            ],
            "csrf": "preserve-and-explicit",
            "authorization": "default-deny-and-explicit",
            "validation": "explicit-binding-boundaries",
            "transactions": "explicit-service-boundaries",
            "targetBuild": "NOT_RUN",
            "provenance": _generated_provenance(model, snapshot, files),
        }
    elif profile.kind == "jsp":
        files = _jsp_preservation_files()
        payload = {
            "viewStrategy": "preserve",
            "jspViews": list(model.ir["views"]),
            "modernization": "deferred-independent-wave",
            "packaging": "traditional-war",
            "files": files,
            "fileDigests": {
                path: canonical_digest(content) for path, content in files.items()
            },
            "viewContract": {
                "prefix": "/WEB-INF/jsp/",
                "suffix": ".jsp",
                "dispatchKinds": ["forward", "redirect", "include"],
            },
            "targetBuild": "NOT_RUN",
            "browserVerification": "NOT_RUN",
        }
    else:
        payload = {"changes": [], "reason": "unsupported transform profile"}
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",),
        confidence=0.68,
    )


def _source_map(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(
            request, profile, "repository_root is required for source mapping"
        )
    generated = _generate_controllers(model, "source-map")
    target_digest = canonical_digest(generated)
    mappings = []
    for endpoint in model.ir["endpoints"]:
        filename = _controller_path(endpoint)
        mappings.append(
            {
                "id": "map:" + endpoint["id"].removeprefix("endpoint:"),
                "legacyEvidenceRefs": endpoint["evidenceRefs"],
                "irNodeRefs": [endpoint["id"], endpoint["pipelineId"]],
                "decisionRefs": ["decision:preserve-first"],
                "targetLocations": [
                    {"uri": "target://" + filename, "lineStart": 1, "lineEnd": 80}
                ],
                "testRefs": ["scenario:" + endpoint["id"].removeprefix("endpoint:")],
                "verificationRefs": [],
                "recipe": {
                    "id": "org.elmos.legacyweb.IRDrivenController",
                    "version": "1.0.0",
                },
                "modelGeneration": None,
            }
        )
    return _success(
        request,
        profile,
        {
            "mapVersion": "1.0.0",
            "repositorySnapshotId": snapshot.digest,
            "targetDigest": target_digest,
            "mappings": mappings,
        },
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",),
        confidence=0.8,
    )


def _change_set(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    change_set = request.inputs.get("change_set")
    if not isinstance(change_set, Mapping):
        if model is None or snapshot is None:
            return _blocked(
                request, profile, "change_set or repository_root is required"
            )
        generated = _generate_controllers(model, "change-set")
        generated.update(_target_support_files())
        change_set = {
            "files": generated,
            "sourceSnapshotDigest": snapshot.digest,
            "producer": request.skill_id,
        }
    try:
        files = validate_generated_files(
            change_set.get("files", {}) if isinstance(change_set, Mapping) else {}
        )
    except TransformationError as exc:
        return _blocked(request, profile, str(exc))
    content = finite_json({**dict(change_set), "files": files})
    digest = canonical_digest(content)
    payload = {
        "changeSetId": "changeset:" + digest.removeprefix("sha256:")[:24],
        "digest": digest,
        "state": "STAGED",
        "idempotencyKey": request.idempotency_key,
        "fencingToken": request.authority.fencing_token,
        "gitMutation": False,
        "committed": False,
        "commitProtocol": "content-addressed-private-staging/v1",
        "reversible": True,
        "content": content,
    }
    if request.authority.profile != "transform":
        payload["blockedReason"] = (
            "transform authority is required to publish a staged change set"
        )
        return CapabilityResult(
            skill_id=request.skill_id,
            handler_id="legacy-web:" + request.skill_id,
            state="BLOCKED",
            code="TRANSFORM_AUTHORITY_REQUIRED",
            artifacts=(_artifact(request, profile, payload, confidence=0.0),),
            warnings=(payload["blockedReason"],),
            unavailable=profile.unavailable,
        )
    return _success(request, profile, payload, confidence=0.85)


def _verification(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if profile.kind in {"coverage", "scenarios"} and (
        model is None or snapshot is None
    ):
        return _blocked(
            request, profile, "repository_root is required for verification planning"
        )
    supplied_runtime_data = (
        (
            profile.kind in {"http-oracle", "state-oracle", "security-oracle"}
            and "observations" in request.inputs
        )
        or (
            profile.kind == "runtime-verification"
            and "runtime_observations" in request.inputs
        )
        or (profile.kind == "trace" and "traces" in request.inputs)
    )
    if supplied_runtime_data and request.authority.profile not in {
        "test-sandbox",
        "build-sandbox",
    }:
        return _blocked(
            request,
            profile,
            "test-sandbox or build-sandbox authority is required to evaluate runtime observations",
        )
    if profile.kind == "coverage":
        payload = _coverage(model)
    elif profile.kind == "scenarios":
        payload = _behavior_contract(model, snapshot)
    elif profile.kind in {"http-oracle", "state-oracle", "security-oracle"}:
        try:
            payload = evaluate_equivalence(request.inputs, oracle_kind=profile.kind)
        except VerificationError as exc:
            return _blocked(request, profile, str(exc))
    elif profile.kind == "runtime-verification":
        try:
            payload = evaluate_runtime_workload(request.inputs)
        except VerificationError as exc:
            return _blocked(request, profile, str(exc))
    elif profile.kind == "trace":
        try:
            payload = correlate_traces(request.inputs)
        except VerificationError as exc:
            return _blocked(request, profile, str(exc))
    else:
        payload = {"status": "NOT_RUN"}
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (),
        confidence=0.7 if profile.kind != "http-oracle" else 0.4,
    )


def _repair(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    if profile.kind == "mismatch":
        mismatches = request.inputs.get("mismatches", [])
        payload = {
            "mismatches": [
                _classify(item) for item in mismatches if isinstance(item, Mapping)
            ],
            "firstDivergenceRequired": True,
            "sourceBaselineMutation": False,
        }
    elif profile.kind == "repair":
        try:
            payload = bounded_repair(request.inputs)
        except GovernanceError as exc:
            return _blocked(request, profile, str(exc))
    else:
        payload = {
            "selected": _select_regressions(
                request.inputs.get("mismatches", []), model
            ),
            "selectionBasis": ["source-map", "IR dependencies", "first divergence"],
            "independentCorpus": "holdout-required",
        }
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (),
        confidence=0.65,
    )


def _certification(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    try:
        payload = certification_bundle(
            request,
            snapshot_digest=snapshot.digest if snapshot else None,
            unknowns=list(model.unknowns) if model else [],
            risks=list(_risk_register(model).get("risks", [])) if model else [],
        )
    except GovernanceError as exc:
        return _blocked(request, profile, str(exc))
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (),
        confidence=0.45,
    )


def _benchmark(
    request: RuntimeRequest,
    profile: OperationProfile,
    model: ForensicModel | None,
    snapshot: RepositorySnapshot | None,
) -> CapabilityResult:
    try:
        payload = benchmark_scorecard(
            request.inputs,
            snapshot_digest=snapshot.digest if snapshot else None,
            route_count=len(model.routes) if model else 0,
        )
    except GovernanceError as exc:
        return _blocked(request, profile, str(exc))
    return _success(
        request,
        profile,
        payload,
        evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (),
        confidence=0.4,
    )


def _success(
    request: RuntimeRequest,
    profile: OperationProfile,
    payload: Mapping[str, Any],
    *,
    evidence_refs: tuple[str, ...] = (),
    confidence: float = 0.7,
) -> CapabilityResult:
    artifact = _artifact(
        request,
        profile,
        payload,
        evidence_refs=evidence_refs,
        confidence=confidence,
        input_hashes=(canonical_digest(request.inputs),),
    )
    return CapabilityResult(
        skill_id=request.skill_id,
        handler_id="legacy-web:" + request.skill_id,
        state=profile.state,
        code=profile.code,
        artifacts=(artifact,),
        unavailable=profile.unavailable,
    )


def execute_profile(
    request: RuntimeRequest, profile: OperationProfile
) -> CapabilityResult:
    snapshot, model = _model(request)
    if profile.kind == "orchestrator":
        return _orchestrator(request, profile)
    if profile.kind == "contract":
        return _contract(request, profile)
    if profile.kind == "snapshot":
        if snapshot is None:
            return _blocked(
                request, profile, "repository_root is required to capture a snapshot"
            )
        return _success(
            request,
            profile,
            snapshot.manifest(),
            evidence_refs=(f"ev:snapshot:{snapshot.digest}",),
            confidence=1.0,
        )
    if profile.kind == "checkpoint":
        return _checkpoint(request, profile)
    if profile.kind == "eta":
        return _eta(request, profile)
    if profile.kind == "authority":
        return _authority(request, profile)
    if profile.kind in {
        "modules",
        "frameworks",
        "runtime",
        "routes",
        "config",
        "dependencies",
    }:
        return _forensic(request, profile, model, snapshot)
    if profile.kind == "recovery":
        return _recovery(request, profile, model, snapshot)
    if profile.kind in {"graph", "ir", "behavior", "unknowns", "risk"}:
        return _model_operation(request, profile, model, snapshot)
    if profile.kind in {"strategy", "target", "waves", "shims", "packaging", "cutover"}:
        return _plan(request, profile, model, snapshot)
    if profile.kind in {"rewrite", "generator", "jakarta", "security-generator", "jsp"}:
        return _transform(request, profile, model, snapshot)
    if profile.kind == "source-map":
        return _source_map(request, profile, model, snapshot)
    if profile.kind == "change-set":
        return _change_set(request, profile, model, snapshot)
    if profile.kind in {
        "coverage",
        "scenarios",
        "http-oracle",
        "state-oracle",
        "security-oracle",
        "runtime-verification",
        "trace",
    }:
        return _verification(request, profile, model, snapshot)
    if profile.kind in {"mismatch", "repair", "regression"}:
        return _repair(request, profile, model, snapshot)
    if profile.kind == "cutover-runbook":
        plan = compile_cutover_plan(
            request,
            route_ids=[str(item["id"]) for item in model.routes] if model else [],
            snapshot_digest=snapshot.digest if snapshot else "NOT_RUN",
        )
        return _success(
            request,
            profile,
            evaluate_cutover_runbook(request, plan),
            evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (),
            confidence=0.82,
        )
    if profile.kind == "certification":
        return _certification(request, profile, model, snapshot)
    if profile.kind == "benchmark":
        return _benchmark(request, profile, model, snapshot)
    return _blocked(request, profile, "no operation implementation is registered")


def _route_conflicts(routes: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for route in routes:
        groups[(route["pathPattern"], tuple(route["methods"]))].append(route)
    return [
        {
            "pathPattern": key[0],
            "methods": list(key[1]),
            "owners": [item["owner"] for item in values],
            "severity": "critical",
        }
        for key, values in groups.items()
        if len(values) > 1
    ]


def _jakarta_readiness(dependencies: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    javax = [item for item in dependencies if item["namespace"] == "javax"]
    legacy = [
        item
        for item in dependencies
        if "struts" in item["coordinate"] or "ognl" in item["coordinate"]
    ]
    return {
        "javaxCount": len(javax),
        "legacyFrameworkCount": len(legacy),
        "mixedNamespace": bool(
            javax and any(item["namespace"] == "jakarta" for item in dependencies)
        ),
        "status": "blocked"
        if legacy
        else "needs-review"
        if javax
        else "ready-for-target-analysis",
    }


def _behavior_contract(
    model: ForensicModel | None, snapshot: RepositorySnapshot | None
) -> dict[str, Any]:
    scenarios = []
    for endpoint in model.routes if model else ():
        step_id = "request:" + endpoint["id"].removeprefix("endpoint:")
        scenarios.append(
            {
                "id": "scenario:" + endpoint["id"].removeprefix("endpoint:"),
                "name": endpoint["methods"][0] + " " + endpoint["pathPattern"],
                "risk": endpoint["criticality"],
                "preconditions": [{"identity": "approved-test-principal-required"}],
                "steps": [
                    {
                        "id": step_id,
                        "request": {
                            "method": endpoint["methods"][0],
                            "path": endpoint["pathPattern"],
                            "form": {},
                        },
                        "clock": "controlled",
                        "identity": {"session": "redacted", "user": "redacted"},
                        "expectedState": {"route": endpoint["id"]},
                    }
                ],
                "assertions": [
                    {
                        "path": "response.status",
                        "op": "in",
                        "value": [200, 302, 303, 400, 401, 403, 404, 500],
                    },
                    {
                        "path": "dispatch.kind",
                        "op": "in",
                        "value": [nav["kind"] for nav in endpoint["navigation"]],
                    },
                ],
                "normalizers": ["NORM-TRACE-ID", "NORM-SESSION-ID"],
                "evidenceRefs": endpoint["evidenceRefs"],
            }
        )
    return {
        "contractVersion": "1.0.0",
        "repositorySnapshotId": snapshot.digest if snapshot else "unknown",
        "scenarios": scenarios,
    }


def _risk_register(model: ForensicModel | None) -> dict[str, Any]:
    risks = []
    if model:
        for unknown in model.unknowns:
            risks.append(
                {
                    "id": "risk:" + unknown["id"],
                    "category": unknown["category"],
                    "severity": unknown["severity"],
                    "score": 1.0 if unknown["severity"] == "critical" else 0.75,
                    "status": "open",
                    "unknownRef": unknown["id"],
                    "mitigation": unknown["resolutionPlan"],
                }
            )
        for route in _route_conflicts(model.routes):
            risks.append(
                {
                    "id": "risk:route-conflict:"
                    + hashlib.sha256(str(route).encode()).hexdigest()[:12],
                    "category": "route",
                    "severity": "critical",
                    "score": 1.0,
                    "status": "open",
                    "mitigation": ["assign explicit Strangler owner"],
                }
            )
    return {
        "riskVersion": "1.0.0",
        "risks": risks,
        "verificationBudget": {
            "critical": sum(item["severity"] == "critical" for item in risks),
            "high": sum(item["severity"] == "high" for item in risks),
        },
    }


def _is_exact_target(target: Mapping[str, Any]) -> bool:
    required = (
        "springBoot",
        "springFramework",
        "jakartaEE",
        "servlet",
        "java",
        "packaging",
    )
    return all(
        key in target and target[key] not in {None, "", "4.x", "7.x"}
        for key in required
    )


def _wave_plan(model: ForensicModel) -> dict[str, Any]:
    units = []
    for index, module in enumerate(model.modules):
        routes = [
            route["id"]
            for route in model.routes
            if route["owner"]["symbol"]
            and (module["name"] in route["owner"]["symbol"] or index == 0)
        ]
        units.append(
            {
                "id": "unit:" + module["id"].removeprefix("module:"),
                "modules": [module["id"]],
                "routes": routes,
                "risk": "critical" if routes else "high",
                "dependsOn": ["unit:foundation"] if index else [],
                "changes": ["PrepareSpringBoot4Baseline", "MigrateJakartaNamespaces"],
                "verification": ["compile", "startup", "differential-scenarios"],
                "rollback": {"type": "route-to-legacy"},
            }
        )
    return {"units": units, "parallelism": 1, "independentHoldoutRequired": True}


def _namespace_changes(
    snapshot: RepositorySnapshot, *, jakarta: bool
) -> dict[str, Any]:
    return namespace_change_set(snapshot, jakarta=jakarta)["files"]


def _resolved_target(request: RuntimeRequest) -> dict[str, Any]:
    value = request.inputs.get("target")
    target = dict(value) if isinstance(value, Mapping) else {}
    target.setdefault("springBoot", "4.0.0")
    target.setdefault("springFramework", "7.0.1")
    target.setdefault("jakartaEE", "11")
    target.setdefault("servlet", "6.1")
    target.setdefault("java", 21)
    target.setdefault("packaging", "war")
    return target


def _target_support_files() -> dict[str, str]:
    return {
        "src/main/java/org/elmos/legacyweb/generated/LegacyNavigationResolver.java": """package org.elmos.legacyweb.generated;

public final class LegacyNavigationResolver {
    public String forward(String path) { return \"forward:\" + requirePath(path); }
    public String redirect(String path) { return \"redirect:\" + requirePath(path); }
    private String requirePath(String path) {
        if (path == null || !path.startsWith(\"/\")) throw new IllegalArgumentException(\"absolute application path required\");
        return path;
    }
}
""",
        "src/main/java/org/elmos/legacyweb/generated/LegacyRequestLifecycle.java": """package org.elmos.legacyweb.generated;

public interface LegacyRequestLifecycle {
    void reset();
    void populate();
    void validate();
    void invoke();
}
""",
        "src/main/java/org/elmos/legacyweb/generated/LegacyInvocationPipeline.java": """package org.elmos.legacyweb.generated;

import java.util.Map;

public interface LegacyInvocationPipeline {
    String invoke(String legacyOwner, Map<String, String> bindings, String dispatchKind, String target);
}
""",
    }


def _generated_provenance(
    model: ForensicModel, snapshot: RepositorySnapshot, files: Mapping[str, str]
) -> dict[str, Any]:
    return {
        "sourceSnapshotDigest": snapshot.digest,
        "irDigest": canonical_digest(model.ir),
        "generatorVersion": "legacy-web-generator/2.0.0",
        "outputDigest": canonical_digest(dict(files)),
        "recipes": [
            "IRDrivenController/v2",
            "LegacyNavigationResolver/v1",
            "ExplicitBinding/v1",
        ],
    }


def _controller_path(endpoint: Mapping[str, Any]) -> str:
    symbol = _java_identifier(
        str(endpoint["owner"]["symbol"]).split(".")[-1].replace("$", "_")
    )
    route_suffix = hashlib.sha256(str(endpoint["id"]).encode("utf-8")).hexdigest()[:10]
    return f"src/main/java/org/elmos/legacyweb/generated/{symbol}_{route_suffix}Controller.java"


def _java_identifier(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value) or "GeneratedType"
    if result[0].isdigit():
        result = "Generated_" + result
    return result


def _java_string(value: Any) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "\\r")
        .replace("\n", "\\n")
    )


def _generate_controllers(model: ForensicModel, reason: str) -> dict[str, str]:
    files: dict[str, str] = {}
    bindings = {item["id"]: item for item in model.ir.get("bindings", [])}
    framework_filter = (
        "struts1"
        if "STRUTS1" in reason
        else "struts2"
        if "STRUTS2" in reason
        else "servlet"
        if "SERVLET" in reason
        else None
    )
    for endpoint in model.ir["endpoints"]:
        if endpoint["owner"]["framework"] not in {"struts1", "struts2", "servlet"}:
            continue
        if (
            framework_filter is not None
            and endpoint["owner"]["framework"] != framework_filter
        ):
            continue
        method = (
            endpoint["methods"][0]
            if endpoint["methods"][0]
            in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"}
            else "GET"
        )
        class_name = Path(_controller_path(endpoint)).stem
        params = []
        entries = []
        seen_variables: set[str] = set()
        for binding_id in endpoint.get("bindingIds", []):
            binding = bindings.get(binding_id)
            if binding is None:
                continue
            source_name = str(binding["sourceName"])
            variable = re.sub(r"[^A-Za-z0-9_]", "_", source_name) or "requestValue"
            if variable[0].isdigit():
                variable = "value_" + variable
            if variable in seen_variables:
                variable += (
                    "_" + hashlib.sha256(source_name.encode("utf-8")).hexdigest()[:6]
                )
            seen_variables.add(variable)
            params.append(
                f'@RequestParam(name = "{_java_string(source_name)}", required = {str(bool(binding.get("required"))).lower()}) String {variable}'
            )
            entries.append(f'Map.entry("{_java_string(source_name)}", {variable})')
        navigation = endpoint.get("navigation", [])
        target = next(
            (item.get("target") for item in navigation if item.get("target")),
            "/WEB-INF/jsp/legacy-preserved.jsp",
        )
        kind = next(
            (item.get("kind") for item in navigation if item.get("target")), "forward"
        )
        values = (
            "Map.of()" if not entries else "Map.ofEntries(" + ", ".join(entries) + ")"
        )
        body = [
            "package org.elmos.legacyweb.generated;",
            "",
            "import java.util.Map;",
            "import org.springframework.stereotype.Controller;",
            "import org.springframework.web.bind.annotation.RequestMapping;",
            "import org.springframework.web.bind.annotation.RequestMethod;",
            "import org.springframework.web.bind.annotation.RequestParam;",
            "",
            "@Controller",
            f"public final class {class_name} {{",
            "    private final LegacyInvocationPipeline pipeline;",
            f"    public {class_name}(LegacyInvocationPipeline pipeline) {{ this.pipeline = pipeline; }}",
            "",
            f'    @RequestMapping(path = "{_java_string(endpoint["pathPattern"])}", method = RequestMethod.{method})',
            f"    public String handle({', '.join(params)}) {{",
            f'        return pipeline.invoke("{_java_string(endpoint["owner"]["symbol"])}", {values}, "{_java_string(str(kind))}", "{_java_string(str(target))}");',
            "    }",
            "}",
            "",
        ]
        files[_controller_path(endpoint)] = "\n".join(body)
    return files


def _security_config(model: ForensicModel) -> str:
    rules = (
        ", ".join(f'"{rule["id"]}"' for rule in model.ir.get("securityRules", []))
        or "/* no confirmed rule; fail closed */"
    )
    return "\n".join(
        [
            "package org.elmos.legacyweb;",
            "",
            "import org.springframework.context.annotation.Bean;",
            "import org.springframework.context.annotation.Configuration;",
            "import org.springframework.security.config.annotation.web.builders.HttpSecurity;",
            "import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;",
            "import org.springframework.security.config.Customizer;",
            "import org.springframework.security.web.SecurityFilterChain;",
            "",
            "@Configuration",
            "@EnableWebSecurity",
            "public final class LegacySecurityConfiguration {",
            f"    static final String[] CONFIRMED_RULES = {{{rules}}};",
            "",
            "    @Bean",
            "    SecurityFilterChain legacySecurityFilterChain(HttpSecurity http) throws Exception {",
            "        // Default deny prevents an unverified route from becoming public.",
            "        http.authorizeHttpRequests(authorize -> authorize.anyRequest().denyAll());",
            "        http.csrf(Customizer.withDefaults());",
            "        return http.build();",
            "    }",
            "}",
            "",
        ]
    )


def _security_validation_transaction_files(model: ForensicModel) -> dict[str, str]:
    return {
        "src/main/java/org/elmos/legacyweb/LegacySecurityConfiguration.java": _security_config(
            model
        ),
        "src/main/java/org/elmos/legacyweb/generated/LegacyValidationBoundary.java": """package org.elmos.legacyweb.generated;

import jakarta.validation.Validator;

public final class LegacyValidationBoundary {
    private final Validator validator;
    public LegacyValidationBoundary(Validator validator) { this.validator = validator; }
    public void requireValid(Object value) {
        var violations = validator.validate(value);
        if (!violations.isEmpty()) throw new IllegalArgumentException(\"legacy validation rejected request\");
    }
}
""",
        "src/main/java/org/elmos/legacyweb/generated/LegacyTransactionalService.java": """package org.elmos.legacyweb.generated;

import java.util.function.Supplier;
import org.springframework.transaction.annotation.Transactional;

public final class LegacyTransactionalService {
    @Transactional(rollbackFor = Exception.class)
    public <T> T execute(Supplier<T> work) { return work.get(); }
}
""",
    }


def _jsp_preservation_files() -> dict[str, str]:
    return {
        "src/main/java/org/elmos/legacyweb/LegacyJspViewConfiguration.java": """package org.elmos.legacyweb;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.view.InternalResourceViewResolver;

@Configuration
public final class LegacyJspViewConfiguration {
    @Bean
    InternalResourceViewResolver legacyJspViewResolver() {
        var resolver = new InternalResourceViewResolver();
        resolver.setPrefix(\"/WEB-INF/jsp/\");
        resolver.setSuffix(\".jsp\");
        return resolver;
    }
}
""",
        "src/main/resources/application-legacy-jsp.yaml": "spring:\n  mvc:\n    view:\n      prefix: /WEB-INF/jsp/\n      suffix: .jsp\n",
    }


def _coverage(model: ForensicModel) -> dict[str, Any]:
    endpoints = len(model.routes)
    confirmed = sum(bool(item.get("evidenceRefs")) for item in model.routes)
    unknowns = len(model.unknowns)
    return {
        "snapshot": {"denominator": 1, "verified": 1, "coverage": 1.0},
        "route": {
            "denominator": endpoints,
            "verified": confirmed,
            "coverage": confirmed / endpoints if endpoints else 0.0,
        },
        "ir": {
            "denominator": endpoints,
            "verified": confirmed,
            "coverage": confirmed / endpoints if endpoints else 0.0,
        },
        "sourceMap": {"denominator": endpoints, "verified": 0, "coverage": 0.0},
        "criticalUnknowns": sum(
            item["severity"] == "critical" for item in model.unknowns
        ),
        "unknowns": unknowns,
    }


def _classify(item: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(item)
    value.setdefault("classification", "unknown-first-divergence")
    value.setdefault("rootCauseId", None)
    value["sourceBaselineMutation"] = False
    return value


def _select_regressions(mismatches: Any, model: ForensicModel | None) -> list[str]:
    selected = []
    if isinstance(mismatches, list):
        for item in mismatches:
            if isinstance(item, Mapping) and item.get("scenarioId"):
                selected.append(str(item["scenarioId"]))
    if not selected and model:
        selected = [
            "scenario:" + route["id"].removeprefix("endpoint:")
            for route in model.routes[:32]
        ]
    return sorted(set(selected))
