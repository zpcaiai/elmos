"""Capability-specific operations for all 55 legacy-web Skills."""

from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
import hashlib
import re
from typing import Any, Mapping
from pathlib import Path

from .analysis import ForensicModel, build_forensic_model
from .catalog import PACKAGE_DIRECTORY, validate_artifact_payload
from .canonical import canonical_digest, finite_json, redact_json, redact_text
from .contracts import ArtifactEnvelope, CapabilityResult, RuntimeRequest, utc_now
from .external_evidence import not_run_external_status
from .java_ast_toolkit import JavaLexer
from .snapshot import RepositorySnapshot, capture_repository


@dataclass(frozen=True, slots=True)
class OperationProfile:
    code: str
    artifact_type: str
    state: str
    kind: str
    unavailable: tuple[str, ...] = ()


def _profile(code: str, artifact_type: str, kind: str, *, state: str = "LOCAL_EXECUTED", unavailable: tuple[str, ...] = ()) -> OperationProfile:
    return OperationProfile(code=code, artifact_type=artifact_type, state=state, kind=kind, unavailable=unavailable)


PROFILES: dict[str, OperationProfile] = {
    "00-modernization-orchestrator": _profile("RUN_MANIFEST_COMPILED", "run-manifest", "orchestrator"),
    "01-job-contract-and-policy-resolver": _profile("JOB_CONTRACT_RESOLVED", "job-contract", "contract"),
    "02-reproducible-repository-snapshot": _profile("REPOSITORY_SNAPSHOT_CAPTURED", "repository-snapshot", "snapshot"),
    "03-checkpoint-resume-cancel": _profile("CHECKPOINT_POLICY_COMPILED", "execution-checkpoint", "checkpoint"),
    "04-wall-clock-eta-and-cost-model": _profile("WALL_CLOCK_ESTIMATE_COMPILED", "wall-clock-estimate", "eta"),
    "05-tool-authority-and-sandbox": _profile("AUTHORITY_PLAN_COMPILED", "authority-plan", "authority"),
    "10-build-and-module-topology": _profile("BUILD_TOPOLOGY_RECOVERED", "build-topology", "modules", unavailable=("native-maven-build",)),
    "11-framework-and-version-fingerprinting": _profile("FRAMEWORK_INVENTORY_RECOVERED", "framework-inventory", "frameworks"),
    "12-runtime-deployment-topology": _profile("RUNTIME_TOPOLOGY_RECOVERED", "runtime-topology", "runtime", unavailable=("running-container",)),
    "13-route-ownership-and-conflict-analysis": _profile("EFFECTIVE_ROUTE_TABLE_RECOVERED", "route-table", "routes"),
    "14-environment-config-overlay-analysis": _profile("CONFIG_OVERLAYS_RECOVERED", "config-overlay", "config"),
    "15-dependency-compatibility-and-jakarta-readiness": _profile("JAKARTA_READINESS_SCORED", "dependency-compatibility", "dependencies"),
    "20-struts1-lifecycle-recovery": _profile("STRUTS1_PIPELINES_RECOVERED", "struts1-pipeline", "recovery"),
    "21-struts2-interceptor-pipeline-recovery": _profile("STRUTS2_PIPELINES_RECOVERED", "struts2-pipeline", "recovery"),
    "22-servlet-container-semantics-recovery": _profile("SERVLET_SEMANTICS_RECOVERED", "servlet-container-ir", "recovery"),
    "23-jsp-taglib-and-view-semantics": _profile("VIEW_SEMANTICS_RECOVERED", "view-semantics", "recovery"),
    "24-request-binding-and-type-conversion": _profile("BINDING_CONVERSION_RECOVERED", "binding-conversion-ir", "recovery"),
    "25-navigation-dispatch-and-error-semantics": _profile("NAVIGATION_SEMANTICS_RECOVERED", "navigation-dispatch-ir", "recovery"),
    "26-session-state-and-scope-semantics": _profile("STATE_SCOPE_RECOVERED", "state-scope-ir", "recovery"),
    "27-security-authn-authz-csrf-semantics": _profile("SECURITY_SEMANTICS_RECOVERED", "security-semantics-ir", "recovery"),
    "28-transaction-and-side-effect-topology": _profile("EFFECT_TOPOLOGY_RECOVERED", "transaction-effect-ir", "recovery"),
    "29-concurrency-lifecycle-and-threadlocal": _profile("CONCURRENCY_SEMANTICS_RECOVERED", "concurrency-lifecycle-ir", "recovery"),
    "30-repository-evidence-graph": _profile("EVIDENCE_GRAPH_BUILT", "repository-evidence-graph", "graph"),
    "31-legacy-web-semantic-ir": _profile("LEGACY_WEB_IR_BUILT", "legacy-web-semantic-ir", "ir"),
    "32-behavioral-contract-and-sequence-mining": _profile("BEHAVIOR_CONTRACTS_MINED", "behavior-contract", "behavior"),
    "33-unknown-semantics-ledger": _profile("UNKNOWN_LEDGER_BUILT", "unknown-semantics-ledger", "unknowns"),
    "34-semantic-risk-scoring": _profile("SEMANTIC_RISKS_SCORED", "semantic-risk-register", "risk"),
    "40-preserve-first-migration-strategy": _profile("PRESERVE_FIRST_STRATEGY_COMPILED", "migration-strategy", "strategy"),
    "41-springboot4-target-architecture": _profile("SPRINGBOOT4_TARGET_COMPILED", "target-architecture", "target"),
    "42-multi-module-conversion-wave-planner": _profile("CONVERSION_WAVES_COMPILED", "conversion-wave-plan", "waves"),
    "43-compatibility-shim-synthesis": _profile("COMPATIBILITY_SHIMS_COMPILED", "compatibility-shim-plan", "shims"),
    "44-packaging-view-and-container-decision": _profile("PACKAGING_DECISION_COMPILED", "packaging-decision", "packaging"),
    "45-cutover-strangler-and-dual-run-plan": _profile("CUTOVER_ROLLBACK_PLAN_COMPILED", "cutover-plan", "cutover", state="PLANNING_ONLY", unavailable=("production-cutover",)),
    "50-deterministic-ast-and-config-rewrite": _profile("DETERMINISTIC_REWRITE_PLANNED", "rewrite-change-set", "rewrite", state="PARTIAL_LOCAL_EXECUTED", unavailable=("native-java-ast",)),
    "51-struts1-to-springmvc-generator": _profile("STRUTS1_CONTROLLERS_GENERATED", "generated-target", "generator", state="PARTIAL_LOCAL_EXECUTED", unavailable=("target-build",)),
    "52-struts2-to-springmvc-generator": _profile("STRUTS2_CONTROLLERS_GENERATED", "generated-target", "generator", state="PARTIAL_LOCAL_EXECUTED", unavailable=("target-build",)),
    "53-servlet-to-springmvc-generator": _profile("SERVLET_CONTROLLERS_GENERATED", "generated-target", "generator", state="PARTIAL_LOCAL_EXECUTED", unavailable=("target-build",)),
    "54-jakarta-and-dependency-migration": _profile("JAKARTA_REWRITE_PLANNED", "jakarta-dependency-change-set", "jakarta", state="PARTIAL_LOCAL_EXECUTED", unavailable=("target-build",)),
    "55-spring-security-validation-transaction-generator": _profile("SECURITY_VALIDATION_GENERATED", "security-validation-target", "security-generator", state="PARTIAL_LOCAL_EXECUTED", unavailable=("security-runtime",)),
    "56-jsp-preserve-or-modernize": _profile("JSP_VIEW_DECISION_COMPILED", "jsp-view-decision", "jsp", state="PARTIAL_LOCAL_EXECUTED", unavailable=("browser-view-runtime",)),
    "57-source-map-change-provenance": _profile("SOURCE_MAP_BUILT", "semantic-source-map", "source-map"),
    "58-idempotent-change-set-commit": _profile("CHANGE_SET_COMMIT_PREPARED", "change-set", "change-set", state="PLANNING_ONLY", unavailable=("git-commit",)),
    "60-static-semantic-coverage": _profile("STATIC_SEMANTIC_COVERAGE_MEASURED", "static-semantic-coverage", "coverage"),
    "61-test-and-scenario-generation": _profile("SCENARIOS_GENERATED", "scenario-catalog", "scenarios"),
    "62-differential-http-and-view-oracle": _profile("HTTP_VIEW_ORACLE_EVALUATED", "equivalence-report", "http-oracle", state="PARTIAL_LOCAL_EXECUTED", unavailable=("legacy-target-runners",)),
    "63-session-db-and-side-effect-diff": _profile("STATE_EFFECT_ORACLE_EVALUATED", "equivalence-report", "state-oracle", state="PARTIAL_LOCAL_EXECUTED", unavailable=("database-cdc",)),
    "64-security-equivalence-and-hardening": _profile("SECURITY_ORACLE_EVALUATED", "security-equivalence", "security-oracle", state="PARTIAL_LOCAL_EXECUTED", unavailable=("independent-security-verifier",)),
    "65-concurrency-performance-and-fault-verification": _profile("RUNTIME_STRESS_PLAN_COMPILED", "runtime-verification-plan", "runtime-verification", state="PLANNING_ONLY", unavailable=("browser-runtime", "load-runner", "fault-injector")),
    "66-observability-and-trace-correlation": _profile("TRACE_CORRELATION_COMPILED", "trace-correlation", "trace", state="PARTIAL_LOCAL_EXECUTED", unavailable=("distributed-trace-collector",)),
    "70-mismatch-classification": _profile("MISMATCHES_CLASSIFIED", "mismatch-ledger", "mismatch"),
    "71-bounded-semantic-auto-repair": _profile("BOUNDED_REPAIR_PROPOSED", "repair-change-set", "repair", state="PARTIAL_LOCAL_EXECUTED", unavailable=("automatic-write-to-customer-repository",)),
    "72-impact-based-regression-selection": _profile("IMPACT_REGRESSION_SELECTED", "regression-selection", "regression"),
    "73-production-cutover-rollback": _profile("CUTOVER_RUNBOOK_COMPILED", "cutover-runbook", "cutover-runbook", state="PLANNING_ONLY", unavailable=("production-deployment",)),
    "74-evidence-bundle-and-e0-e5-certification": _profile("CERTIFICATION_GATE_EVALUATED", "certification-bundle", "certification", state="PLANNING_ONLY", unavailable=("independent-verifier", "production-evidence")),
    "75-golden-route-benchmark-and-learning-cache": _profile("GOLDEN_ROUTE_SCORECARD_COMPILED", "golden-route-scorecard", "benchmark", state="PARTIAL_LOCAL_EXECUTED", unavailable=("three-authorized-customer-repositories", "independent-learning-verifier")),
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


def _model(request: RuntimeRequest) -> tuple[RepositorySnapshot | None, ForensicModel | None]:
    snapshot = _snapshot(request)
    return snapshot, build_forensic_model(snapshot) if snapshot is not None else None


def _artifact(request: RuntimeRequest, profile: OperationProfile, payload: Mapping[str, Any], *, evidence_refs: tuple[str, ...] = (), confidence: float = 0.75, input_hashes: tuple[str, ...] = ()) -> ArtifactEnvelope:
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


def _blocked(request: RuntimeRequest, profile: OperationProfile, reason: str) -> CapabilityResult:
    artifact = _artifact(request, profile, {"status": "BLOCKED", "reason": reason, "externalEvidence": "NOT_RUN"}, confidence=0.0)
    return CapabilityResult(skill_id=request.skill_id, handler_id="legacy-web:" + request.skill_id, state="BLOCKED", code="BLOCKED_MISSING_AUTHORITY_OR_INPUT", artifacts=(artifact,), warnings=(reason,), unavailable=profile.unavailable)


def _orchestrator(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    target = request.inputs.get("target", {"framework": "spring-boot", "versionLine": "4.x", "java": 21})
    manifest = {"apiVersion": "elmos.dev/v1", "kind": "RepositoryModernizationJob", "jobId": request.job_id, "tenantId": request.tenant_id, "state": "CREATED", "phaseDag": ["SNAPSHOTTING", "FORENSICS", "SEMANTIC_RECOVERY", "IR_BUILT", "PLANNED", "TRANSFORMING", "BUILDING", "VERIFYING", "REPAIRING", "E4_VERIFIED", "CUTOVER_READY", "E5_CERTIFIED"], "target": target, "authority": {"environmentId": request.authority.environment_id, "profile": request.authority.profile, "approved": request.authority.approved}, "externalEvidence": "NOT_RUN", "certification": "NOT_CERTIFIED"}
    return _success(request, profile, manifest, confidence=0.95)


def _contract(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    target = request.inputs.get("target", {"framework": "spring-boot", "versionLine": "4.x", "java": 21})
    if not isinstance(target, Mapping) or target.get("framework") != "spring-boot":
        return _blocked(request, profile, "target.framework must be spring-boot")
    policy = {"mode": request.inputs.get("mode", "preserve-first"), "view": request.inputs.get("view", "preserve"), "security": request.inputs.get("security", "preserve"), "packaging": request.inputs.get("packaging", "auto"), "cutover": "plan-only", "equivalence": request.inputs.get("equivalence", "strict"), "target": dict(target), "resolvedAt": utc_now()}
    return _success(request, profile, {"jobContract": {"jobId": request.job_id, "source": {"repository": "local-snapshot", "credentialsRef": None}, "target": dict(target), "strategy": policy}, "policySnapshotHash": canonical_digest(policy), "externalEffectsAuthorized": False}, confidence=1.0)


def _checkpoint(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    input_hash = canonical_digest(request.inputs)
    payload = {"jobId": request.job_id, "stepId": request.skill_id, "attemptId": request.request_id, "state": "safe-point", "inputHash": input_hash, "policySnapshotHash": canonical_digest(request.policy), "ownerEnvironmentId": request.authority.environment_id, "leaseId": request.idempotency_key, "fencingToken": request.authority.fencing_token, "artifacts": [], "sideEffects": [], "resumeCursor": {"next": "resume-from-input-hash"}, "createdAt": utc_now()}
    return _success(request, profile, payload, confidence=1.0)


def _eta(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    snapshot, model = _model(request)
    files = len(snapshot.files) if snapshot else int(request.inputs.get("file_count", 0) or 0)
    bytes_total = snapshot.total_bytes if snapshot else int(request.inputs.get("bytes", 0) or 0)
    endpoints = len(model.routes) if model else int(request.inputs.get("endpoint_count", 0) or 0)
    loc = sum((item.text or "").count("\n") + 1 for item in snapshot.files) if snapshot else int(request.inputs.get("loc", 0) or 0)
    base = max(1.0, files * 0.02 + bytes_total / 8_000_000 + endpoints * 0.8 + loc / 10_000)
    phases = [{"phase": phase, "p50": round(base * multiplier, 3)} for phase, multiplier in (("transformation", 1.0), ("verification", 1.6), ("repair-certification", 0.7))]
    p50 = sum(item["p50"] for item in phases)
    payload = {"estimateVersion": "1.0.0", "jobId": request.job_id, "asOf": utc_now(), "unit": "seconds", "p50": round(p50, 3), "p80": round(p50 * 1.5, 3), "p95": round(p50 * 2.0, 3), "remainingPhases": phases, "confidence": 0.55 if not snapshot else 0.72, "features": {"loc": loc, "files": files, "bytes": bytes_total, "endpoints": endpoints, "cacheHit": 0.0}, "assumptions": ["machine wall-clock only", "human approval wait excluded", "external provider/runtime evidence unavailable"], "humanWaitExcluded": True, "model": {"id": "legacy-web-eta-v1", "version": "1.0.0"}}
    return _success(request, profile, payload, confidence=payload["confidence"])


def _authority(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    payload = {"profile": request.authority.profile, "environmentId": request.authority.environment_id, "scopes": list(request.authority.scopes), "fencingToken": request.authority.fencing_token, "approved": request.authority.approved, "policy": {"filesystem": "repository-read" if request.authority.profile == "scan-readonly" else "staged-workspace", "network": "deny", "database": "none", "secrets": "none"}, "externalEffectsAllowed": False}
    return _success(request, profile, payload, confidence=1.0)


def _forensic(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(request, profile, "repository_root is required for repository forensics")
    values: dict[str, Any] = {
        "modules": list(model.modules), "frameworks": list(model.framework_inventory), "runtime": model.runtime_topology, "routes": list(model.routes), "configOverlays": list(model.config_overlays), "dependencies": list(model.dependencies), "unknowns": list(model.unknowns), "snapshotDigest": snapshot.digest,
    }
    selected = {
        "modules": {"modules": values["modules"]}, "frameworks": {"frameworks": values["frameworks"]}, "runtime": {"runtime": values["runtime"]}, "routes": {"routes": values["routes"], "conflicts": _route_conflicts(model.routes)}, "config": {"overlays": values["configOverlays"]}, "dependencies": {"dependencies": values["dependencies"], "jakartaReadiness": _jakarta_readiness(model.dependencies)},
    }.get(profile.kind, values)
    return _success(request, profile, selected, evidence_refs=(f"ev:snapshot:{snapshot.digest}",), confidence=0.82)


def _recovery(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(request, profile, "repository_root is required for semantic recovery")
    recovery = model.recovery
    if profile.kind == "recovery":
        payload = {"snapshotDigest": snapshot.digest, "recovered": recovery, "frameworks": [item["name"] for item in model.framework_inventory], "preservationPolicy": "preserve-first", "unknownRefs": [item["id"] for item in model.unknowns]}
    else:
        payload = {"snapshotDigest": snapshot.digest, "recovered": recovery}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",), confidence=0.78)


def _model_operation(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(request, profile, "repository_root is required for semantic modeling")
    if profile.kind == "graph": payload = model.graph
    elif profile.kind == "ir": payload = model.ir
    elif profile.kind == "behavior": payload = _behavior_contract(model, snapshot)
    elif profile.kind == "unknowns": payload = {"ledgerVersion": "1.0.0", "items": list(model.unknowns)}
    else: payload = _risk_register(model)
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",), confidence=0.76 if model.unknowns else 0.9)


def _plan(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if profile.kind in {"strategy", "target", "waves", "shims", "packaging", "cutover"} and model is None:
        return _blocked(request, profile, "repository_root is required to plan a repository migration")
    target = dict(request.inputs.get("target", {"springBoot": "4.x", "springFramework": "7.x", "jakartaEE": "11", "servlet": "6.1", "java": 21, "packaging": "mixed"}))
    if profile.kind == "strategy": payload = {"strategy": "preserve-first", "allowedDeltas": [], "preserved": ["route", "session", "security", "transaction", "database", "effects", "JSP"], "deferred": ["JSP-to-React", "domain-refactor", "database-schema-refactor"]}
    elif profile.kind == "target": payload = {"target": target, "exactTuple": _is_exact_target(target), "maintenanceOwner": request.inputs.get("maintenance_owner", "unassigned"), "dependencyLockPolicy": "required", "supportedJava": [17, 21, 25], "externalEvidence": "NOT_RUN"}
    elif profile.kind == "waves": payload = _wave_plan(model)
    elif profile.kind == "shims": payload = {"compatibilityShims": [{"id": "shim:legacy-navigation", "purpose": "preserve forward/redirect/include distinction", "removalGate": "all navigation contracts verified"}, {"id": "shim:form-binding", "purpose": "preserve ActionForm reset/populate/validation ordering", "removalGate": "all binding contracts migrated"}]}
    elif profile.kind == "packaging": payload = {"decision": "traditional-war" if any(module["packaging"] in {"war", "ear"} for module in model.modules) else "jar", "view": "preserve-jsp", "container": "external-container-required-until-proven", "reasons": ["preserve-first", "runtime container semantics are not statically complete"]}
    else: payload = {"mode": "route-canary", "stages": [0, 1, 5, 25, 100], "rollbackOn": ["critical mismatch", "error-rate threshold", "database effect mismatch"], "productionExecution": False, "approvalRequired": True}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (), confidence=0.72)


def _transform(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(request, profile, "repository_root is required for IR-driven transformation")
    if profile.kind in {"rewrite", "jakarta"}:
        changes = _namespace_changes(snapshot, jakarta=profile.kind == "jakarta")
        payload = {"mode": "staged-only", "changes": changes, "changedFiles": len(changes), "sourceSnapshotDigest": snapshot.digest, "targetBuild": "NOT_RUN", "gitMutation": False}
    elif profile.kind == "generator":
        files, obligations = _generate_controllers(model, profile.code, snapshot)
        payload = {"mode": "staged-only", "target": {"springBoot": "4.x", "springFramework": "7.x", "jakartaEE": "11", "servlet": "6.1", "java": 21}, "files": files, "semanticObligations": obligations, "sourceSnapshotDigest": snapshot.digest, "targetBuild": "NOT_RUN", "gitMutation": False}
    elif profile.kind == "security-generator":
        payload = {"files": {"src/main/java/org/elmos/legacyweb/LegacySecurityConfiguration.java": _security_config(model)}, "allowlistedBindings": [binding["sourceName"] for binding in model.ir.get("bindings", [])], "csrf": "preserve-and-explicit", "authorization": "preserve-and-explicit", "targetBuild": "NOT_RUN"}
    elif profile.kind == "jsp":
        translated, blockers, source_map = _translate_jsp_views(snapshot)
        payload = {"viewStrategy": "thymeleaf-candidate" if translated and not blockers else "hybrid-preserve", "jspViews": list(model.ir["views"]), "files": translated, "blockingObligations": blockers, "sourceMap": source_map, "modernization": "deterministic-supported-subset", "packaging": "executable-jar-candidate" if translated and not blockers else "traditional-war", "targetBuild": "NOT_RUN"}
    else:
        payload = {"changes": [], "reason": "unsupported transform profile"}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",), confidence=0.68)


def _source_map(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if model is None or snapshot is None:
        return _blocked(request, profile, "repository_root is required for source mapping")
    generated, _ = _generate_controllers(model, "source-map", snapshot)
    target_digest = canonical_digest(generated)
    mappings = []
    for endpoint in model.ir["endpoints"]:
        filename = _controller_path(endpoint)
        mappings.append({"id": "map:" + endpoint["id"].removeprefix("endpoint:"), "legacyEvidenceRefs": endpoint["evidenceRefs"], "irNodeRefs": [endpoint["id"], endpoint["pipelineId"]], "decisionRefs": ["decision:preserve-first"], "targetLocations": [{"uri": "target://" + filename, "lineStart": 1, "lineEnd": 80}], "testRefs": ["scenario:" + endpoint["id"].removeprefix("endpoint:")], "verificationRefs": [], "recipe": {"id": "org.elmos.legacyweb.IRDrivenController", "version": "1.0.0"}, "modelGeneration": None})
    return _success(request, profile, {"mapVersion": "1.0.0", "repositorySnapshotId": snapshot.digest, "targetDigest": target_digest, "mappings": mappings}, evidence_refs=(f"ev:snapshot:{snapshot.digest}",), confidence=0.8)


def _change_set(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    change_set = request.inputs.get("change_set")
    if not isinstance(change_set, Mapping):
        if model is None or snapshot is None:
            return _blocked(request, profile, "change_set or repository_root is required")
        generated, obligations = _generate_controllers(model, "change-set", snapshot)
        change_set = {"files": generated, "semanticObligations": obligations, "sourceSnapshotDigest": snapshot.digest}
    digest = canonical_digest(change_set)
    payload = {"changeSetId": "changeset:" + digest.removeprefix("sha256:")[:24], "digest": digest, "state": "STAGED", "idempotencyKey": request.idempotency_key, "fencingToken": request.authority.fencing_token, "gitMutation": False, "committed": False, "reversible": True, "payload": finite_json(dict(change_set))}
    if request.authority.profile != "transform":
        payload["blockedReason"] = "transform authority is required to publish a staged change set"
        return CapabilityResult(skill_id=request.skill_id, handler_id="legacy-web:" + request.skill_id, state="BLOCKED", code="TRANSFORM_AUTHORITY_REQUIRED", artifacts=(_artifact(request, profile, payload, confidence=0.0),), warnings=(payload["blockedReason"],), unavailable=profile.unavailable)
    return _success(request, profile, payload, confidence=0.85)


def _verification(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if profile.kind in {"coverage", "scenarios"} and (model is None or snapshot is None):
        return _blocked(request, profile, "repository_root is required for verification planning")
    if profile.kind == "coverage":
        payload = _coverage(model)
    elif profile.kind == "scenarios":
        payload = _behavior_contract(model, snapshot)
    elif profile.kind in {"http-oracle", "state-oracle", "security-oracle"}:
        payload = _equivalence(request, model, snapshot, profile.kind)
    elif profile.kind == "runtime-verification":
        payload = {"status": "NOT_RUN", "scenarios": ["parallel-session", "threadlocal-cleanup", "async-dispatch", "timeout", "connection-pool-exhaustion"], "browserRuntime": "NOT_RUN", "loadRunner": "NOT_RUN", "faultInjector": "NOT_RUN"}
    else:
        payload = {"status": "NOT_RUN"}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (), confidence=0.7 if profile.kind != "http-oracle" else 0.4)


def _repair(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    if profile.kind == "mismatch":
        mismatches = request.inputs.get("mismatches", [])
        payload = {"mismatches": [_classify(item) for item in mismatches if isinstance(item, Mapping)], "firstDivergenceRequired": True, "sourceBaselineMutation": False}
    elif profile.kind == "repair":
        mismatch = request.inputs.get("mismatch")
        if not isinstance(mismatch, Mapping):
            return _blocked(request, profile, "mismatch is required for bounded repair")
        payload = {"rootCauseId": mismatch.get("rootCauseId") or "root-cause:unresolved", "changes": [], "newFalsifiableTests": ["targeted-replay-required"], "maxIterations": 5, "maxChangedFiles": 12, "maxChangedLoc": 800, "applied": False, "requiresApproval": True, "forbiddenActions": ["weaken-tests", "disable-authz", "swallow-exceptions", "no-op-writes"]}
    else:
        payload = {"selected": _select_regressions(request.inputs.get("mismatches", []), model), "selectionBasis": ["source-map", "IR dependencies", "first divergence"], "independentCorpus": "holdout-required"}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (), confidence=0.65)


def _certification(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    metrics = request.inputs.get("metrics", {})
    if not isinstance(metrics, Mapping):
        metrics = {}
    unknowns = list(model.unknowns) if model else []
    critical_unknowns = sum(item.get("severity") == "critical" for item in unknowns)
    external = not_run_external_status()
    external_gate = {
        "id": "EXTERNAL_EVIDENCE",
        "status": "blocked",
        "evidenceStatus": external["evidence_status"],
        "decision": external["decision"],
        "requiredEvidenceTypes": external["required_evidence_types"],
        "certification": external["certification"],
    }
    payload = {"bundleVersion": "1.0.0", "jobId": request.job_id, "level": "E1" if model and critical_unknowns == 0 else "BLOCKED", "issuedAt": utc_now(), "policySnapshotHash": canonical_digest(request.policy), "repositorySnapshotId": snapshot.digest if snapshot else "NOT_RUN", "targetDigest": request.inputs.get("target_digest", "NOT_RUN"), "artifacts": [], "gates": [{"id": "E0", "status": "passed" if snapshot else "blocked"}, {"id": "E1", "status": "passed" if model and critical_unknowns == 0 else "blocked"}, external_gate], "unknowns": unknowns, "risks": list(_risk_register(model).get("risks", [])) if model else [], "metrics": dict(metrics), "reproducibility": {"commands": ["make legacy-web-modernization-skills"], "environmentDigests": [canonical_digest({"python": "local", "engine": "1.0.0"})]}}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (), confidence=0.45)


def _benchmark(request: RuntimeRequest, profile: OperationProfile, model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> CapabilityResult:
    routes = len(model.routes) if model else 0
    payload = {"benchmarkVersion": "1.0.0", "scope": {"routes": routes, "authorizedRepositories": int(request.inputs.get("authorized_repositories", 0) or 0)}, "metrics": {"routeCount": routes, "criticalRouteCoverage": 0.0, "firstPassRate": None, "repairIterations": None, "wallClockSeconds": None}, "cache": {"state": "candidate-only", "key": canonical_digest({"snapshot": snapshot.digest if snapshot else None, "engine": "1.0.0"}), "independentValidation": "NOT_RUN"}, "productionCertification": "NOT_CERTIFIED"}
    return _success(request, profile, payload, evidence_refs=(f"ev:snapshot:{snapshot.digest}",) if snapshot else (), confidence=0.4)


def _success(request: RuntimeRequest, profile: OperationProfile, payload: Mapping[str, Any], *, evidence_refs: tuple[str, ...] = (), confidence: float = 0.7) -> CapabilityResult:
    artifact = _artifact(request, profile, payload, evidence_refs=evidence_refs, confidence=confidence, input_hashes=(canonical_digest(request.inputs),))
    return CapabilityResult(skill_id=request.skill_id, handler_id="legacy-web:" + request.skill_id, state=profile.state, code=profile.code, artifacts=(artifact,), unavailable=profile.unavailable)


def execute_profile(request: RuntimeRequest, profile: OperationProfile) -> CapabilityResult:
    snapshot, model = _model(request)
    if profile.kind == "orchestrator": return _orchestrator(request, profile)
    if profile.kind == "contract": return _contract(request, profile)
    if profile.kind == "snapshot":
        if snapshot is None: return _blocked(request, profile, "repository_root is required to capture a snapshot")
        return _success(request, profile, snapshot.manifest(), evidence_refs=(f"ev:snapshot:{snapshot.digest}",), confidence=1.0)
    if profile.kind == "checkpoint": return _checkpoint(request, profile)
    if profile.kind == "eta": return _eta(request, profile)
    if profile.kind == "authority": return _authority(request, profile)
    if profile.kind in {"modules", "frameworks", "runtime", "routes", "config", "dependencies"}: return _forensic(request, profile, model, snapshot)
    if profile.kind == "recovery": return _recovery(request, profile, model, snapshot)
    if profile.kind in {"graph", "ir", "behavior", "unknowns", "risk"}: return _model_operation(request, profile, model, snapshot)
    if profile.kind in {"strategy", "target", "waves", "shims", "packaging", "cutover"}: return _plan(request, profile, model, snapshot)
    if profile.kind in {"rewrite", "generator", "jakarta", "security-generator", "jsp"}: return _transform(request, profile, model, snapshot)
    if profile.kind == "source-map": return _source_map(request, profile, model, snapshot)
    if profile.kind == "change-set": return _change_set(request, profile, model, snapshot)
    if profile.kind in {"coverage", "scenarios", "http-oracle", "state-oracle", "security-oracle", "runtime-verification"}: return _verification(request, profile, model, snapshot)
    if profile.kind in {"mismatch", "repair", "regression"}: return _repair(request, profile, model, snapshot)
    if profile.kind == "cutover-runbook": return _success(request, profile, {"runbookVersion": "1.0.0", "mode": "plan-only", "steps": ["freeze route owner", "shadow traffic with capture", "compare hard-gate dimensions", "canary by approved route", "rollback on critical mismatch"], "execution": "NOT_RUN", "productionMutation": False}, confidence=0.65)
    if profile.kind == "certification": return _certification(request, profile, model, snapshot)
    if profile.kind == "benchmark": return _benchmark(request, profile, model, snapshot)
    return _blocked(request, profile, "no operation implementation is registered")


def _route_conflicts(routes: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for route in routes: groups[(route["pathPattern"], tuple(route["methods"]))].append(route)
    return [{"pathPattern": key[0], "methods": list(key[1]), "owners": [item["owner"] for item in values], "severity": "critical"} for key, values in groups.items() if len(values) > 1]


def _jakarta_readiness(dependencies: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    javax = [item for item in dependencies if item["namespace"] == "javax"]
    legacy = [item for item in dependencies if "struts" in item["coordinate"] or "ognl" in item["coordinate"]]
    return {"javaxCount": len(javax), "legacyFrameworkCount": len(legacy), "mixedNamespace": bool(javax and any(item["namespace"] == "jakarta" for item in dependencies)), "status": "blocked" if legacy else "needs-review" if javax else "ready-for-target-analysis"}


def _behavior_contract(model: ForensicModel | None, snapshot: RepositorySnapshot | None) -> dict[str, Any]:
    scenarios = []
    for endpoint in (model.routes if model else ()):
        step_id = "request:" + endpoint["id"].removeprefix("endpoint:")
        scenarios.append({"id": "scenario:" + endpoint["id"].removeprefix("endpoint:"), "name": endpoint["methods"][0] + " " + endpoint["pathPattern"], "risk": endpoint["criticality"], "preconditions": [{"identity": "approved-test-principal-required"}], "steps": [{"id": step_id, "request": {"method": endpoint["methods"][0], "path": endpoint["pathPattern"], "form": {}}, "clock": "controlled", "identity": {"session": "redacted", "user": "redacted"}, "expectedState": {"route": endpoint["id"]}}], "assertions": [{"path": "response.status", "op": "in", "value": [200, 302, 303, 400, 401, 403, 404, 500]}, {"path": "dispatch.kind", "op": "in", "value": [nav["kind"] for nav in endpoint["navigation"]]}], "normalizers": ["NORM-TRACE-ID", "NORM-SESSION-ID"], "evidenceRefs": endpoint["evidenceRefs"]})
    return {"contractVersion": "1.0.0", "repositorySnapshotId": snapshot.digest if snapshot else "unknown", "scenarios": scenarios}


def _risk_register(model: ForensicModel | None) -> dict[str, Any]:
    risks = []
    if model:
        for unknown in model.unknowns:
            risks.append({"id": "risk:" + unknown["id"], "category": unknown["category"], "severity": unknown["severity"], "score": 1.0 if unknown["severity"] == "critical" else 0.75, "status": "open", "unknownRef": unknown["id"], "mitigation": unknown["resolutionPlan"]})
        for route in _route_conflicts(model.routes):
            risks.append({"id": "risk:route-conflict:" + hashlib.sha256(str(route).encode()).hexdigest()[:12], "category": "route", "severity": "critical", "score": 1.0, "status": "open", "mitigation": ["assign explicit Strangler owner"]})
    return {"riskVersion": "1.0.0", "risks": risks, "verificationBudget": {"critical": sum(item["severity"] == "critical" for item in risks), "high": sum(item["severity"] == "high" for item in risks)}}


def _is_exact_target(target: Mapping[str, Any]) -> bool:
    required = ("springBoot", "springFramework", "jakartaEE", "servlet", "java", "packaging")
    return all(key in target and target[key] not in {None, "", "4.x", "7.x"} for key in required)


def _wave_plan(model: ForensicModel) -> dict[str, Any]:
    units = []
    for index, module in enumerate(model.modules):
        routes = [route["id"] for route in model.routes if route["owner"]["symbol"] and (module["name"] in route["owner"]["symbol"] or index == 0)]
        units.append({"id": "unit:" + module["id"].removeprefix("module:"), "modules": [module["id"]], "routes": routes, "risk": "critical" if routes else "high", "dependsOn": ["unit:foundation"] if index else [], "changes": ["PrepareSpringBoot4Baseline", "MigrateJakartaNamespaces"], "verification": ["compile", "startup", "differential-scenarios"], "rollback": {"type": "route-to-legacy"}})
    return {"units": units, "parallelism": 1, "independentHoldoutRequired": True}


def _namespace_changes(snapshot: RepositorySnapshot, *, jakarta: bool) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    replacements = (("javax.servlet", "jakarta.servlet"), ("javax.validation", "jakarta.validation"), ("javax.annotation", "jakarta.annotation"), ("javax.persistence", "jakarta.persistence"))
    for file in snapshot.files:
        if file.kind != "file" or file.text is None or not file.path.endswith((".java", ".xml", ".properties", ".yml", ".yaml")):
            continue
        before = file.text
        after = before
        applied = []
        if jakarta:
            for old, new in replacements:
                if old in after:
                    after = after.replace(old, new); applied.append({"from": old, "to": new})
        if after != before:
            safe_after = redact_text(after)
            changes[file.path] = {"beforeDigest": file.digest, "afterDigest": canonical_digest(safe_after), "content": safe_after, "replacements": applied, "parser": "java-import-or-structured-config-rewrite"}
    return changes


def _controller_path(endpoint: Mapping[str, Any]) -> str:
    symbol = _java_identifier(str(endpoint["owner"]["symbol"]).split(".")[-1].replace("$", "_"))
    return f"src/main/java/org/elmos/legacyweb/generated/{symbol}Controller.java"


def _java_identifier(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value) or "GeneratedType"
    if result[0].isdigit():
        result = "Generated_" + result
    return result


def _binding_variable(value: Any) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", str(value)) or "requestValue"
    return "value_" + result if result[0].isdigit() else result


def _java_string(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")


def _generate_controllers(model: ForensicModel, reason: str, snapshot: RepositorySnapshot | None = None) -> tuple[dict[str, str], list[dict[str, Any]]]:
    files: dict[str, str] = {}
    obligations: list[dict[str, Any]] = []
    bindings = {item["id"]: item for item in model.ir.get("bindings", [])}
    for endpoint in model.ir["endpoints"]:
        if endpoint["owner"]["framework"] not in {"struts1", "struts2", "servlet"}:
            continue
        annotations = ["@Controller"]
        method_annotation = f'    @RequestMapping(path = "{_java_string(endpoint["pathPattern"])}", method = RequestMethod.{endpoint["methods"][0]})'
        class_name = _java_identifier(str(endpoint["owner"]["symbol"]).split(".")[-1].replace("$", "_")) + "Controller"
        params = []
        for binding_id in endpoint.get("bindingIds", []):
            binding = bindings.get(binding_id)
            if binding is None:
                continue
            source_name = str(binding["sourceName"])
            variable = _binding_variable(source_name)
            params.append(f'@RequestParam(name = "{_java_string(source_name)}", required = {str(bool(binding.get("required"))).lower()}) String {variable}')
        navigation = endpoint.get("navigation", [])
        target = next((item.get("target") for item in navigation if item.get("target")), "/WEB-INF/jsp/legacy-preserved.jsp")
        kind = next((item.get("kind") for item in navigation if item.get("target")), "forward")
        prefix = "redirect: " if kind == "redirect" else "forward: "
        action_semantics = _recover_action_semantics(snapshot, endpoint)
        port_name = class_name.removesuffix("Controller") + "UseCase"
        constructor = [f"    private final {port_name} useCase;", "", f"    public {class_name}({port_name} useCase) {{", "        this.useCase = useCase;", "    }", ""]
        input_values = ", ".join(_binding_variable(bindings[item]["sourceName"]) for item in endpoint.get("bindingIds", []) if item in bindings)
        invocation = [f"        {port_name}.Outcome outcome = useCase.execute(new {port_name}.Input({input_values}));", "        return switch (outcome.result()) {"]
        navigation_cases = []
        for item in navigation:
            if not item.get("target"):
                continue
            nav_prefix = "redirect: " if item.get("kind") == "redirect" else "forward: "
            navigation_cases.append(f'            case "{_java_string(item.get("when", "success"))}" -> "{_java_string(nav_prefix + str(item["target"]))}";')
        invocation.extend(navigation_cases or [f'            case "success" -> "{_java_string(prefix + str(target))}";'])
        invocation.extend(["            default -> throw new IllegalStateException(\"Unmapped legacy action result: \" + outcome.result());", "        };", "    }"])
        body = ["package org.elmos.legacyweb.generated;", "", "import org.springframework.stereotype.Controller;", "import org.springframework.web.bind.annotation.RequestMapping;", "import org.springframework.web.bind.annotation.RequestMethod;", "import org.springframework.web.bind.annotation.RequestParam;", "", *annotations, f"public final class {class_name} {{", f"    // Generated from {_java_string(endpoint['owner']['symbol'])} using {_java_string(reason)}.", *constructor, method_annotation, f"    public String handle({', '.join(params)}) {{", *invocation, "}", ""]
        files[_controller_path(endpoint)] = "\n".join(body)
        input_components = ", ".join(f"String {_binding_variable(bindings[item]['sourceName'])}" for item in endpoint.get("bindingIds", []) if item in bindings)
        port_body = ["package org.elmos.legacyweb.generated;", "", f"public interface {port_name} {{", f"    record Input({input_components}) {{}}", "    record Outcome(String result) {", "        public Outcome {", "            if (result == null || result.isBlank()) throw new IllegalArgumentException(\"legacy result is required\");", "        }", "    }", "", "    Outcome execute(Input input);", "}", ""]
        port_path = _controller_path(endpoint).replace("Controller.java", "UseCase.java")
        files[port_path] = "\n".join(port_body)
        translated_body, translation_blockers = _translate_action_body(
            action_semantics,
            [_binding_variable(bindings[item]["sourceName"]) for item in endpoint.get("bindingIds", []) if item in bindings],
            port_name,
        )
        if translated_body is not None:
            adapter_path = port_path.replace("UseCase.java", "UseCaseAdapter.java")
            files[adapter_path] = "\n".join([
                "package org.elmos.legacyweb.generated;",
                "",
                "import org.springframework.stereotype.Component;",
                "",
                "@Component",
                f"public final class {port_name}Adapter implements {port_name} {{",
                "    @Override",
                "    public Outcome execute(Input input) {",
                *["        " + line for line in translated_body],
                "    }",
                "}",
                "",
            ])
            obligations.append({"endpointId": endpoint["id"], "severity": "medium", "reason": "replay generated use-case adapter against the legacy action before cutover", "sourceMethod": action_semantics["method"], "sourceBodyDigest": action_semantics["bodyDigest"], "translation": "deterministic-supported-subset", "blocks": ["behavior-equivalence"]})
        elif action_semantics["method"] is None:
            obligations.append({"endpointId": endpoint["id"], "severity": "critical", "reason": "action entry method was not structurally recovered", "blocks": ["target-build", "behavior-equivalence"]})
        else:
            obligations.append({"endpointId": endpoint["id"], "severity": "high", "reason": "implement use-case port from recovered action body before cutover", "sourceMethod": action_semantics["method"], "sourceBodyDigest": action_semantics["bodyDigest"], "returnExpressions": action_semantics["returnExpressions"], "unsupportedStatements": translation_blockers, "blocks": ["behavior-equivalence"]})
    return files, obligations


def _recover_action_semantics(snapshot: RepositorySnapshot | None, endpoint: Mapping[str, Any]) -> dict[str, Any]:
    if snapshot is None:
        return {"method": None, "bodyDigest": None, "returnExpressions": [], "body": None, "sourcePath": None}
    symbol = str(endpoint["owner"]["symbol"])
    class_name = symbol.split(".")[-1]
    candidates = [item for item in snapshot.files if item.kind == "file" and item.text is not None and item.path.endswith("/" + class_name + ".java")]
    for candidate in candidates:
        source = candidate.text or ""
        tokens = JavaLexer(source).tokenize(include_trivia=False)
        for method_name in ("execute", "perform", "doExecute"):
            for index, token in enumerate(tokens[:-1]):
                if token.value != method_name or tokens[index + 1].value != "(":
                    continue
                cursor = index + 1
                parentheses = 0
                while cursor < len(tokens):
                    if tokens[cursor].value == "(": parentheses += 1
                    elif tokens[cursor].value == ")":
                        parentheses -= 1
                        if parentheses == 0:
                            break
                    cursor += 1
                cursor += 1
                while cursor < len(tokens) and tokens[cursor].value not in {"{", ";"}:
                    cursor += 1
                if cursor >= len(tokens) or tokens[cursor].value != "{":
                    continue
                open_brace = tokens[cursor]
                braces = 1
                cursor += 1
                while cursor < len(tokens) and braces:
                    if tokens[cursor].value == "{": braces += 1
                    elif tokens[cursor].value == "}": braces -= 1
                    cursor += 1
                if braces:
                    continue
                close_brace = tokens[cursor - 1]
                body = source[open_brace.end_pos:close_brace.start_pos]
                returns = [match.group(1).strip() for match in re.finditer(r"\breturn\s+([^;]+);", body)]
                return {"method": f"{symbol}#{method_name}", "bodyDigest": canonical_digest(body), "returnExpressions": returns, "body": body, "sourcePath": candidate.path}
    return {"method": None, "bodyDigest": None, "returnExpressions": [], "body": None, "sourcePath": None}


def _translate_action_body(action: Mapping[str, Any], bindings: list[str], port_name: str) -> tuple[list[str] | None, list[str]]:
    """Translate only a small, structurally explicit Struts action subset.

    Anything involving control flow, session/request writes, OGNL/ValueStack,
    service calls or exception handling is rejected rather than emitted as
    uncompilable or behavior-changing code.
    """
    body = action.get("body")
    if not isinstance(body, str):
        return None, ["action body unavailable"]
    scrubbed = re.sub(r"/\*[\s\S]*?\*/|//[^\n]*", "", body).strip()
    if not scrubbed:
        return None, ["empty action body"]
    if any(token in scrubbed for token in ("{", "}", "try ", "catch ", "finally", "ValueStack", "ActionContext", "getSession(", "setAttribute(")):
        return None, ["control-flow, state, exception or OGNL semantics require manual extraction"]

    statements = [item.strip() for item in scrubbed.split(";") if item.strip()]
    translated: list[str] = []
    blockers: list[str] = []
    returned = False
    binding_set = set(bindings)
    for statement in statements:
        request_parameter = re.fullmatch(
            r"(?:final\s+)?String\s+([A-Za-z_$][\w$]*)\s*=\s*request\.getParameter\(\s*\"([^\"]+)\"\s*\)",
            statement,
        )
        if request_parameter:
            variable = request_parameter.group(1)
            binding = _binding_variable(request_parameter.group(2))
            if binding not in binding_set:
                blockers.append(f"request parameter {request_parameter.group(2)} is absent from recovered bindings")
            else:
                translated.append(f"String {variable} = input.{binding}();")
            continue
        form_getter = re.fullmatch(
            r"(?:final\s+)?String\s+([A-Za-z_$][\w$]*)\s*=\s*(?:\(\([^)]+\)\s*form\)|form)\.get([A-Z][A-Za-z0-9_$]*)\(\)",
            statement,
        )
        if form_getter:
            binding = _binding_variable(form_getter.group(2)[0].lower() + form_getter.group(2)[1:])
            if binding not in binding_set:
                blockers.append(f"form property {binding} is absent from recovered bindings")
            else:
                translated.append(f"String {form_getter.group(1)} = input.{binding}();")
            continue
        forward = re.fullmatch(r"return\s+mapping\.findForward\(\s*\"([^\"]+)\"\s*\)", statement)
        literal = re.fullmatch(r"return\s+\"([^\"]+)\"", statement)
        constant = re.fullmatch(r"return\s+(SUCCESS|ERROR|INPUT|LOGIN|NONE)", statement)
        result = forward.group(1) if forward else literal.group(1) if literal else constant.group(1).lower() if constant else None
        if result is not None:
            translated.append(f'return new {port_name}.Outcome("{_java_string(result)}");')
            returned = True
            continue
        blockers.append("unsupported statement digest " + canonical_digest(statement))
    if blockers or not returned:
        if not returned:
            blockers.append("no deterministic Struts navigation return was recovered")
        return None, blockers
    return translated, []


def _translate_jsp_views(snapshot: RepositorySnapshot) -> tuple[dict[str, str], list[dict[str, Any]], list[dict[str, Any]]]:
    files: dict[str, str] = {}
    blockers: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for source in snapshot.files:
        if source.kind != "file" or source.text is None or not source.path.endswith(".jsp"):
            continue
        unsupported = sorted(set(re.findall(r"<((?:fmt|sql|x|tiles|display):[A-Za-z0-9_-]+)", source.text)))
        scriptlets = bool(re.search(r"<%(?!@|--)[\s\S]*?%>", source.text))
        if unsupported or scriptlets:
            blockers.append({"source": source.path, "severity": "critical", "unsupportedTags": unsupported, "scriptlet": scriptlets, "blocks": ["view-equivalence", "jar-packaging"]})
            continue
        translated = re.sub(r"<%@\s*(?:taglib|page)[\s\S]*?%>\s*", "", source.text)
        translated = re.sub(r'<(?:c:out|bean:write)\s+(?:value|name)="(?:\$\{)?([^"}]+)\}?"\s*/>', r'<span th:text="${\1}"></span>', translated)
        translated = re.sub(r'<c:if\s+test="([^"]+)">', r'<th:block th:if="\1">', translated).replace("</c:if>", "</th:block>")
        translated = re.sub(r'<c:forEach\s+var="([^"]+)"\s+items="([^"]+)">', r'<th:block th:each="\1 : \2">', translated).replace("</c:forEach>", "</th:block>")
        translated = re.sub(r'<html:form\s+action="([^"]+)">', r'<form th:action="@{\1}" method="post">', translated).replace("</html:form>", "</form>")
        translated = re.sub(r'<html:text\s+property="([^"]+)"\s*/>', r'<input type="text" th:field="*{\1}"/>', translated)
        if "xmlns:th=" not in translated:
            if re.search(r"<html(?:\s|>)", translated, re.IGNORECASE):
                translated = re.sub(r"<html", '<html xmlns:th="http://www.thymeleaf.org"', translated, count=1, flags=re.IGNORECASE)
            else:
                translated = '<html xmlns:th="http://www.thymeleaf.org"><body>\n' + translated + "\n</body></html>"
        relative = source.path
        for prefix in ("src/main/webapp/WEB-INF/jsp/", "src/main/webapp/WEB-INF/views/", "WEB-INF/jsp/", "WEB-INF/views/"):
            if relative.startswith(prefix):
                relative = relative[len(prefix):]
                break
        target = "src/main/resources/templates/" + relative.removesuffix(".jsp") + ".html"
        files[target] = translated
        mappings.append({"source": source.path, "target": target, "sourceDigest": source.digest, "targetDigest": canonical_digest(translated), "translator": "jsp-jstl-thymeleaf-supported-subset-v1"})
    return files, blockers, mappings


def _security_config(model: ForensicModel) -> str:
    rules = ", ".join(f'"{rule["id"]}"' for rule in model.ir.get("securityRules", [])) or "/* no confirmed rule; fail closed */"
    return "\n".join(["package org.elmos.legacyweb;", "", "import org.springframework.context.annotation.Bean;", "import org.springframework.context.annotation.Configuration;", "import org.springframework.security.config.annotation.web.builders.HttpSecurity;", "import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;", "import org.springframework.security.config.Customizer;", "import org.springframework.security.web.SecurityFilterChain;", "", "@Configuration", "@EnableWebSecurity", "public final class LegacySecurityConfiguration {", f"    static final String[] CONFIRMED_RULES = {{{rules}}};", "", "    @Bean", "    SecurityFilterChain legacySecurityFilterChain(HttpSecurity http) throws Exception {", "        // Default deny prevents an unverified route from becoming public.", "        http.authorizeHttpRequests(authorize -> authorize.anyRequest().denyAll());", "        http.csrf(Customizer.withDefaults());", "        return http.build();", "    }", "}", ""])


def _coverage(model: ForensicModel) -> dict[str, Any]:
    endpoints = len(model.routes)
    confirmed = sum(bool(item.get("evidenceRefs")) for item in model.routes)
    unknowns = len(model.unknowns)
    return {"snapshot": {"denominator": 1, "verified": 1, "coverage": 1.0}, "route": {"denominator": endpoints, "verified": confirmed, "coverage": confirmed / endpoints if endpoints else 0.0}, "ir": {"denominator": endpoints, "verified": confirmed, "coverage": confirmed / endpoints if endpoints else 0.0}, "sourceMap": {"denominator": endpoints, "verified": 0, "coverage": 0.0}, "criticalUnknowns": sum(item["severity"] == "critical" for item in model.unknowns), "unknowns": unknowns}


def _equivalence(request: RuntimeRequest, model: ForensicModel | None, snapshot: RepositorySnapshot | None, kind: str) -> dict[str, Any]:
    observations = request.inputs.get("observations")
    dimensions = ["route", "protocol", "view", "binding", "validation", "navigation", "session", "security", "transaction", "database", "externalEffects", "concurrency", "performance"]
    if not isinstance(observations, Mapping) or not isinstance(observations.get("legacy"), Mapping) or not isinstance(observations.get("target"), Mapping):
        return {"reportVersion": "1.0.0", "mode": "strict", "legacyArtifact": "NOT_RUN", "targetArtifact": "NOT_RUN", "dimensions": {dimension: {"denominator": 0, "verified": 0, "equivalent": 0, "normalizedEquivalent": 0, "mismatch": 0, "unknown": 1, "confidence": 0.0} for dimension in dimensions}, "mismatches": [], "summary": {"equivalence": 0.0, "criticalMismatches": 0, "unknowns": len(dimensions)}, "gate": {"status": "blocked", "blockingReasons": ["legacy and target observations are required"]}}
    legacy = observations["legacy"]; target = observations["target"]
    result_dims: dict[str, Any] = {}
    mismatches = []
    for dimension in dimensions:
        left = legacy.get(dimension); right = target.get(dimension)
        if left is None or right is None:
            result_dims[dimension] = {"denominator": 1, "verified": 0, "equivalent": 0, "normalizedEquivalent": 0, "mismatch": 0, "unknown": 1, "confidence": 0.0}
            continue
        equal = left == right
        result_dims[dimension] = {"denominator": 1, "verified": 1, "equivalent": int(equal), "normalizedEquivalent": 0, "mismatch": int(not equal), "unknown": 0, "confidence": 1.0}
        if not equal:
            mismatches.append({"id": "mismatch:" + hashlib.sha256((dimension + repr(left) + repr(right)).encode()).hexdigest()[:16], "scenarioId": "scenario:provided", "dimension": dimension, "severity": "critical" if dimension in {"security", "session", "transaction", "database", "externalEffects"} else "high", "classification": "value-difference", "firstDivergence": {"dimension": dimension}, "legacyObservationRef": "observation://legacy/" + dimension, "targetObservationRef": "observation://target/" + dimension, "normalizerApplied": None, "rootCauseId": None})
    verified = sum(item["verified"] for item in result_dims.values())
    equivalent = sum(item["equivalent"] for item in result_dims.values())
    critical = sum(item["severity"] == "critical" for item in mismatches)
    return {"reportVersion": "1.0.0", "mode": "strict", "legacyArtifact": str(observations.get("legacyArtifact", "observation://legacy")), "targetArtifact": str(observations.get("targetArtifact", "observation://target")), "environment": {"class": "caller-supplied-isolated-observation", "clock": "controlled"}, "dimensions": result_dims, "mismatches": mismatches, "summary": {"equivalence": equivalent / verified if verified else 0.0, "criticalMismatches": critical, "unknowns": sum(item["unknown"] for item in result_dims.values())}, "gate": {"status": "passed" if mismatches == [] and all(item["unknown"] == 0 for item in result_dims.values()) else "failed", "blockingReasons": ["critical mismatch" for _ in range(critical)]}}


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
        selected = ["scenario:" + route["id"].removeprefix("endpoint:") for route in model.routes[:32]]
    return sorted(set(selected))
