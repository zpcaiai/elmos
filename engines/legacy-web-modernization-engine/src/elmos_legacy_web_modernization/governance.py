"""Cutover, bounded repair, certification and benchmark governance."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .canonical import canonical_digest, finite_json
from .contracts import RuntimeRequest, utc_now
from .external_evidence import not_run_external_status


class GovernanceError(ValueError):
    pass


def compile_cutover_plan(
    request: RuntimeRequest, *, route_ids: list[str], snapshot_digest: str
) -> dict[str, Any]:
    stages = request.inputs.get("cutover_stages", [0, 1, 5, 25, 50, 100])
    if (
        not isinstance(stages, list)
        or not stages
        or any(isinstance(item, bool) or not isinstance(item, int) for item in stages)
    ):
        raise GovernanceError("cutover stages must be integer percentages")
    if (
        stages != sorted(set(stages))
        or stages[0] != 0
        or stages[-1] != 100
        or any(item < 0 or item > 100 for item in stages)
    ):
        raise GovernanceError(
            "cutover stages must be unique, ordered, and span 0 to 100"
        )
    owner = request.inputs.get("route_owner", "unassigned")
    thresholds = request.inputs.get(
        "cutover_thresholds",
        {"maxErrorRate": 0.01, "maxP95Ratio": 1.20, "criticalMismatches": 0},
    )
    if not isinstance(thresholds, Mapping):
        raise GovernanceError("cutover thresholds must be an object")
    plan_core = {
        "mode": "strangler-route-canary",
        "snapshotDigest": snapshot_digest,
        "routes": sorted(route_ids),
        "routeOwner": str(owner),
        "stages": stages,
        "thresholds": finite_json(dict(thresholds)),
        "preconditions": [
            "source-and-target-build-pass",
            "startup-readiness-pass",
            "behavioral-gate-pass",
            "security-gate-pass",
            "rollback-rehearsal-pass",
            "explicit-production-approval",
        ],
        "transitions": [
            {
                "from": f"CANARY_{stages[index]}",
                "to": f"CANARY_{stages[index + 1]}",
                "requires": "all-hard-gates-pass",
            }
            for index in range(len(stages) - 1)
        ],
        "rollback": {
            "target": "LEGACY_100",
            "trigger": "any-hard-gate-failure",
            "dataPolicy": "reconcile-before-retry",
            "idempotent": True,
        },
    }
    return {
        "planVersion": "2.0.0",
        "planId": "cutover:" + canonical_digest(plan_core)[7:31],
        **plan_core,
        "productionExecution": "NOT_RUN",
        "providerMutation": False,
        "approvalRequired": True,
        "adapterContract": "CutoverAdapter/v1",
    }


def evaluate_cutover_runbook(
    request: RuntimeRequest, plan: Mapping[str, Any]
) -> dict[str, Any]:
    evidence = request.inputs.get("cutover_evidence", {})
    if not isinstance(evidence, Mapping):
        raise GovernanceError("cutover_evidence must be an object")
    required = (
        "sourceBuild",
        "targetBuild",
        "sourceStartup",
        "targetStartup",
        "behavioral",
        "security",
        "rollback",
    )
    missing = [item for item in required if evidence.get(item) != "PASS"]
    approved = (
        request.authority.profile == "production-cutover" and request.authority.approved
    )
    adapter = request.inputs.get("cutover_adapter_receipt")
    adapter_valid = (
        isinstance(adapter, Mapping)
        and adapter.get("status") in {"APPLIED", "ROLLED_BACK"}
        and isinstance(adapter.get("receiptDigest"), str)
    )
    if adapter_valid and not approved:
        raise GovernanceError(
            "a provider receipt cannot be admitted without production-cutover authority"
        )
    if adapter_valid:
        state = str(adapter["status"])
        execution = "AUTHORIZED_ADAPTER_RECEIPT_ADMITTED"
    elif missing:
        state = "BLOCKED_EVIDENCE"
        execution = "NOT_RUN"
    elif not approved:
        state = "READY_FOR_PRODUCTION_APPROVAL"
        execution = "NOT_RUN"
    else:
        state = "READY_FOR_AUTHORIZED_ADAPTER"
        execution = "NOT_RUN"
    return {
        "runbookVersion": "2.0.0",
        "planId": plan["planId"],
        "state": state,
        "steps": [
            "freeze route owner",
            "verify immutable bindings",
            "shadow traffic",
            "evaluate hard gates",
            "advance one canary stage",
            "reconcile side effects",
            "rollback on any unknown or failure",
        ],
        "evidenceChecks": {item: evidence.get(item, "NOT_RUN") for item in required},
        "missingEvidence": missing,
        "authorityApproved": approved,
        "execution": execution,
        "productionMutation": adapter_valid,
        "adapterReceipt": finite_json(dict(adapter)) if adapter_valid else None,
        "rollback": plan["rollback"],
        "replayKey": request.idempotency_key,
    }


_REPAIR_RECIPES: Mapping[str, dict[str, Any]] = {
    "navigation": {
        "recipe": "preserve-dispatch-kind",
        "file": "src/main/java/org/elmos/legacyweb/generated/LegacyNavigationPolicy.java",
        "content": "package org.elmos.legacyweb.generated;\npublic enum LegacyNavigationPolicy { FORWARD, REDIRECT, INCLUDE }\n",
    },
    "binding": {
        "recipe": "explicit-binding-adapter",
        "file": "src/main/java/org/elmos/legacyweb/generated/LegacyBindingPolicy.java",
        "content": "package org.elmos.legacyweb.generated;\npublic record LegacyBindingPolicy(boolean resetBeforePopulate, boolean validateAfterPopulate) {}\n",
    },
    "session": {
        "recipe": "session-scope-guard",
        "file": "src/main/java/org/elmos/legacyweb/generated/LegacySessionGuard.java",
        "content": "package org.elmos.legacyweb.generated;\npublic final class LegacySessionGuard { private LegacySessionGuard() {} }\n",
    },
    "security": {
        "recipe": "fail-closed-security-guard",
        "file": "src/main/java/org/elmos/legacyweb/generated/LegacySecurityGuard.java",
        "content": "package org.elmos.legacyweb.generated;\npublic final class LegacySecurityGuard { public boolean allow(boolean explicitlyAuthorized) { return explicitlyAuthorized; } }\n",
    },
    "transaction": {
        "recipe": "transaction-boundary-marker",
        "file": "src/main/java/org/elmos/legacyweb/generated/LegacyTransactionBoundary.java",
        "content": "package org.elmos.legacyweb.generated;\npublic @interface LegacyTransactionBoundary {}\n",
    },
}


def bounded_repair(inputs: Mapping[str, Any]) -> dict[str, Any]:
    mismatch = inputs.get("mismatch")
    if not isinstance(mismatch, Mapping):
        raise GovernanceError("mismatch is required for bounded repair")
    dimension = str(mismatch.get("dimension", ""))
    recipe = _REPAIR_RECIPES.get(dimension)
    prohibited = any(
        bool(mismatch.get(key))
        for key in (
            "weakenTests",
            "disableAuthorization",
            "swallowExceptions",
            "noopWrites",
        )
    )
    if prohibited:
        raise GovernanceError("repair request contains a prohibited weakening")
    if recipe is None:
        return {
            "rootCauseId": mismatch.get("rootCauseId") or "root-cause:unresolved",
            "status": "BLOCKED_UNSUPPORTED_REPAIR",
            "changes": [],
            "newFalsifiableTests": ["targeted-replay-required"],
            "limits": {"iterations": 5, "files": 12, "loc": 800},
            "applied": False,
            "requiresApproval": True,
        }
    change = {
        "path": recipe["file"],
        "content": recipe["content"],
        "recipe": recipe["recipe"],
        "contentDigest": canonical_digest(recipe["content"]),
        "precondition": "path-absent-or-same-digest",
    }
    return {
        "rootCauseId": mismatch.get("rootCauseId") or "root-cause:" + dimension,
        "status": "REPAIR_CHANGE_SET_GENERATED",
        "changes": [change],
        "newFalsifiableTests": [
            f"replay-{dimension}-mismatch",
            "reject-regression-outside-impacted-routes",
        ],
        "limits": {"iterations": 5, "files": 12, "loc": 800},
        "applied": False,
        "requiresApproval": True,
        "forbiddenActions": [
            "weaken-tests",
            "disable-authz",
            "swallow-exceptions",
            "no-op-writes",
        ],
    }


def certification_bundle(
    request: RuntimeRequest,
    *,
    snapshot_digest: str | None,
    unknowns: list[dict[str, Any]],
    risks: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = request.inputs.get("local_evidence", {})
    if not isinstance(evidence, Mapping):
        raise GovernanceError("local_evidence must be an object")
    artifacts_value = request.inputs.get("evidence_artifacts", [])
    if not isinstance(artifacts_value, list):
        raise GovernanceError("evidence_artifacts must be an array")
    artifacts: list[dict[str, Any]] = []
    for item in artifacts_value:
        if not isinstance(item, Mapping) or not all(
            isinstance(item.get(key), str) for key in ("type", "uri", "digest")
        ):
            raise GovernanceError(
                "each evidence artifact requires type, uri and digest"
            )
        artifacts.append(finite_json(dict(item)))
    critical_unknowns = sum(item.get("severity") == "critical" for item in unknowns)
    gate_specs = (
        ("E0", bool(snapshot_digest), "immutable source snapshot"),
        (
            "E1",
            critical_unknowns == 0 and evidence.get("semanticModel") == "PASS",
            "semantic model with no critical unknown",
        ),
        (
            "E2",
            evidence.get("transformation") == "PASS",
            "deterministic transformation",
        ),
        (
            "E3",
            evidence.get("buildStartup") == "PASS",
            "source and target build/startup",
        ),
        (
            "E4",
            all(
                evidence.get(name) == "PASS"
                for name in (
                    "holdout",
                    "behavioral",
                    "security",
                    "performance",
                    "operability",
                    "sbom",
                    "rollback",
                )
            ),
            "independent production-equivalent verification",
        ),
    )
    gates = []
    highest = "BLOCKED"
    chain_open = True
    for level, condition, description in gate_specs:
        passed = chain_open and condition
        gates.append(
            {
                "id": level,
                "status": "passed" if passed else "blocked",
                "description": description,
            }
        )
        if passed:
            highest = level
        else:
            chain_open = False
    external = not_run_external_status()
    gates.append(
        {
            "id": "EXTERNAL_EVIDENCE",
            "status": "blocked",
            "evidenceStatus": external["evidence_status"],
            "decision": external["decision"],
            "requiredEvidenceTypes": external["required_evidence_types"],
            "certification": external["certification"],
        }
    )
    return {
        "bundleVersion": "2.0.0",
        "jobId": request.job_id,
        "level": highest,
        "issuedAt": utc_now(),
        "policySnapshotHash": canonical_digest(request.policy),
        "repositorySnapshotId": snapshot_digest or "NOT_RUN",
        "targetDigest": str(request.inputs.get("target_digest", "NOT_RUN")),
        "artifacts": artifacts,
        "gates": gates,
        "unknowns": unknowns,
        "risks": risks,
        "metrics": finite_json(dict(request.inputs.get("metrics", {})))
        if isinstance(request.inputs.get("metrics", {}), Mapping)
        else {},
        "reproducibility": {
            "commands": ["make legacy-web-modernization-skills"],
            "environmentDigests": [
                canonical_digest(
                    {"engine": "2.0.0", "authority": request.authority.environment_id}
                )
            ],
        },
        "signatures": [],
    }


def benchmark_scorecard(
    inputs: Mapping[str, Any], *, snapshot_digest: str | None, route_count: int
) -> dict[str, Any]:
    runs = inputs.get("benchmark_runs", [])
    if not isinstance(runs, list):
        raise GovernanceError("benchmark_runs must be an array")
    if len(runs) > 10_000:
        raise GovernanceError("benchmark run count exceeds policy")
    passed = 0
    total_repair = 0
    total_wall = 0.0
    critical_covered = 0
    critical_total = 0
    normalized_runs = []
    for item in runs:
        if not isinstance(item, Mapping):
            raise GovernanceError("benchmark run must be an object")
        wall = item.get("wallClockSeconds", 0)
        repairs = item.get("repairIterations", 0)
        if (
            isinstance(wall, bool)
            or not isinstance(wall, (int, float))
            or not math.isfinite(float(wall))
            or wall < 0
        ):
            raise GovernanceError("wallClockSeconds must be finite and non-negative")
        if isinstance(repairs, bool) or not isinstance(repairs, int) or repairs < 0:
            raise GovernanceError("repairIterations must be non-negative")
        passed += int(bool(item.get("firstPass", False)))
        total_repair += repairs
        total_wall += float(wall)
        critical_total += int(item.get("criticalRoutes", 0) or 0)
        critical_covered += int(item.get("criticalRoutesPassed", 0) or 0)
        normalized_runs.append(finite_json(dict(item)))
    count = len(normalized_runs)
    key_payload = {
        "snapshot": snapshot_digest,
        "engine": "2.0.0",
        "policy": inputs.get("benchmark_policy", {}),
        "runs": normalized_runs,
    }
    cache_key = canonical_digest(key_payload)
    return {
        "benchmarkVersion": "2.0.0",
        "scope": {
            "routes": route_count,
            "authorizedRepositories": int(
                inputs.get("authorized_repositories", 0) or 0
            ),
            "runCount": count,
        },
        "metrics": {
            "routeCount": route_count,
            "criticalRouteCoverage": critical_covered / critical_total
            if critical_total
            else 0.0,
            "firstPassRate": passed / count if count else None,
            "repairIterations": total_repair / count if count else None,
            "wallClockSeconds": total_wall,
        },
        "cache": {
            "state": "PUBLISHABLE_LOCAL" if count else "EMPTY",
            "key": cache_key,
            "contentDigest": canonical_digest(normalized_runs),
            "tenantScoped": True,
            "independentValidation": "NOT_RUN",
        },
        "productionCertification": "NOT_CERTIFIED",
    }
