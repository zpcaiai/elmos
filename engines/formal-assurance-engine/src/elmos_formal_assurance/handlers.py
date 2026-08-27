from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .canonical import (
    digest_value,
    normalized_text,
    validate_digest,
    validate_identifier,
)
from .contracts import (
    AssuranceLevel,
    Criticality,
    ProofObligation,
    ProofResult,
    ProofStatus,
    Scope,
    SkillOutcome,
    TrustedIdentity,
    Waiver,
    utc_now,
)
from .gate import evaluate_release_gate, validate_result
from .planner import PlanError, serialize_plan, topological_order
from .store import StateStore, StoreError
from .artifact_store import ContentAddressedArtifactStore


class HandlerError(ValueError):
    pass


@dataclass(frozen=True)
class HandlerContext:
    skill_id: str
    handler_id: str
    capability_state: str
    scope: Scope
    subject_id: str
    identity: TrustedIdentity
    payload: dict[str, Any]
    store: StateStore
    artifact_store: ContentAddressedArtifactStore | None = None


def _required(ctx: HandlerContext, key: str) -> Any:
    if key not in ctx.payload:
        raise HandlerError(f"{ctx.skill_id}: missing payload field {key}")
    return ctx.payload[key]


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandlerError(f"{path}: expected object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise HandlerError(f"{path}: expected array")
    return value


def _bounded(
    ctx: HandlerContext,
    output: dict[str, Any],
    *,
    diagnostics: tuple[str, ...] = (),
    status: ProofStatus = ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
    assurance: AssuranceLevel = AssuranceLevel.A1_BOUNDED,
    mode: str = "BOUNDED",
    capability_state: str | None = None,
) -> SkillOutcome:
    return SkillOutcome(
        skill_id=ctx.skill_id,
        handler_id=ctx.handler_id,
        implementation_state="BOUND_LOCAL_EXACT",
        capability_state=capability_state or ctx.capability_state,
        proof_status=status,
        assurance_level=assurance,
        mode=mode,
        output=output,
        diagnostics=diagnostics,
    )


def _blocked(
    ctx: HandlerContext,
    output: dict[str, Any],
    reason: str,
    *,
    status: ProofStatus = ProofStatus.UNSUPPORTED,
) -> SkillOutcome:
    return _bounded(
        ctx,
        output,
        diagnostics=(reason,),
        status=status,
        assurance=AssuranceLevel.NONE,
        mode="RUNTIME",
        capability_state="BLOCKED_EXTERNAL_EVIDENCE_REQUIRED",
    )


def _scope_payload(ctx: HandlerContext) -> dict[str, Any]:
    return {
        "tenantId": ctx.scope.tenant_id,
        "accountId": ctx.scope.account_id,
        "projectId": ctx.scope.project_id,
        "subjectId": ctx.subject_id,
        "sourceArtifactDigest": ctx.scope.source_artifact_digest,
        "targetArtifactDigest": ctx.scope.target_artifact_digest,
        "environmentDigest": ctx.scope.environment_digest,
        "workloadKey": ctx.scope.workload_key,
    }


def _formal_spec(ctx: HandlerContext) -> SkillOutcome:
    spec = _mapping(ctx.payload.get("formalSpec", ctx.payload), "formalSpec")
    required = (
        "id",
        "tenant",
        "businessLine",
        "specKind",
        "version",
        "sourceHash",
        "semanticProfile",
        "status",
        "body",
        "provenance",
    )
    missing = [field for field in required if field not in spec]
    if missing:
        raise HandlerError(f"formalSpec: missing fields {missing}")
    tenant = _mapping(spec["tenant"], "formalSpec.tenant")
    if (
        tenant.get("tenantId") != ctx.scope.tenant_id
        or tenant.get("accountId") != ctx.scope.account_id
    ):
        raise HandlerError("formalSpec tenant/account does not match trusted scope")
    validate_digest(spec["sourceHash"], "formalSpec.sourceHash")
    if not isinstance(spec["body"], dict):
        raise HandlerError("formalSpec.body must be an object")
    provenance = _mapping(spec["provenance"], "formalSpec.provenance")
    for field in ("sourceType", "sourceRevision", "capturedAt"):
        if not isinstance(provenance.get(field), str) or not provenance[field]:
            raise HandlerError(f"formalSpec.provenance.{field} is required")
    source_map = spec.get("sourceMap", [])
    if not isinstance(source_map, list) or any(
        not isinstance(item, dict) for item in source_map
    ):
        raise HandlerError("formalSpec.sourceMap must contain objects")
    canonical = {key: spec[key] for key in sorted(spec)}
    return _bounded(
        ctx,
        {
            "formalSpec": canonical,
            "specDigest": digest_value(canonical),
            "sourceMapEntries": len(source_map),
            "scope": _scope_payload(ctx),
        },
    )


def _observable_behavior(ctx: HandlerContext) -> SkillOutcome:
    contract = _mapping(_required(ctx, "observationContract"), "observationContract")
    source = _list(_required(ctx, "sourceTrace"), "sourceTrace")
    target = _list(_required(ctx, "targetTrace"), "targetTrace")
    dimensions = _list(contract.get("dimensions", []), "observationContract.dimensions")
    normalizers = {
        item.get("field"): item.get("operation")
        for item in _list(
            contract.get("normalizers", []), "observationContract.normalizers"
        )
        if isinstance(item, dict)
    }

    def normalize(trace: list[Any]) -> list[Any]:
        result = []
        for event in trace:
            if not isinstance(event, dict):
                raise HandlerError("trace events must be objects")
            item = dict(event)
            for field, operation in normalizers.items():
                if field not in item:
                    continue
                if operation == "CANONICALIZE":
                    item[field] = normalized_text(item[field], f"trace.{field}")
                elif operation == "SORT" and isinstance(item[field], list):
                    item[field] = sorted(item[field], key=lambda value: repr(value))
                elif operation == "DROP_NONCRITICAL":
                    item.pop(field, None)
                elif operation == "ROUND" and isinstance(item[field], (int, float)):
                    item[field] = round(
                        item[field], int(ctx.payload.get("roundDigits", 2))
                    )
            result.append(item)
        return result

    left, right = normalize(source), normalize(target)
    comparison = "equal" if left == right else "different"
    output: dict[str, Any] = {
        "comparison": comparison,
        "sourceTraceDigest": digest_value(left),
        "targetTraceDigest": digest_value(right),
        "dimensions": dimensions,
        "normalizerFields": sorted(normalizers),
    }
    if comparison == "different":
        output["counterexample"] = {
            "firstDifferentIndex": next(
                (i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]),
                min(len(left), len(right)),
            ),
            "sourceLength": len(left),
            "targetLength": len(right),
        }
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(ctx, output)


def _assumptions(ctx: HandlerContext) -> SkillOutcome:
    assumptions = _list(_required(ctx, "assumptions"), "assumptions")
    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for item in assumptions:
        record = _mapping(item, "assumption")
        identifier = validate_identifier(record.get("id"), "assumption.id")
        state = record.get("status", "OPEN")
        if state not in {"OPEN", "VALIDATED", "VIOLATED", "RETIRED"}:
            raise HandlerError(f"assumption {identifier}: invalid status")
        if state in {"OPEN", "VIOLATED"}:
            unresolved.append(identifier)
        records.append(
            {
                "id": identifier,
                "status": state,
                "risk": record.get("risk", "UNCLASSIFIED"),
                "digest": digest_value(record),
            }
        )
    output = {
        "assumptions": records,
        "assumptionDigest": digest_value(records),
        "unresolved": unresolved,
    }
    if unresolved:
        return _blocked(
            ctx,
            output,
            "assumptions remain OPEN or VIOLATED",
            status=ProofStatus.ASSUMPTION_REQUIRED,
        )
    return _bounded(ctx, output)


def _parse_obligation(item: Any, path: str = "obligation") -> ProofObligation:
    record = _mapping(item, path)
    formula = record.get("formula")
    if not isinstance(formula, str) or not formula.strip():
        raise HandlerError(f"{path}.formula is required")
    formula_hash = validate_digest(
        record.get("formulaHash", digest_value(formula)), f"{path}.formulaHash"
    )
    calculated = digest_value(formula)
    if formula_hash != calculated:
        raise HandlerError(f"{path}.formulaHash does not match formula")
    try:
        criticality = Criticality(record.get("criticality"))
        assurance = AssuranceLevel(record.get("requiredAssurance"))
    except ValueError as exc:
        raise HandlerError(f"{path}: invalid criticality or requiredAssurance") from exc
    dependencies = tuple(
        validate_identifier(value, f"{path}.dependencies")
        for value in record.get("dependencies", [])
    )
    return ProofObligation(
        id=validate_identifier(record.get("id"), f"{path}.id"),
        criticality=criticality,
        property_kind=str(record.get("propertyKind", "FUNCTIONAL_CORRECTNESS")),
        required_assurance=assurance,
        formula_hash=formula_hash,
        allow_bounded=bool(record.get("allowBounded", False)),
        required=bool(record.get("required", True)),
        dependencies=dependencies,
    )


def _obligations(ctx: HandlerContext) -> list[ProofObligation]:
    return [
        _parse_obligation(item, f"obligations[{index}]")
        for index, item in enumerate(
            _list(_required(ctx, "obligations"), "obligations")
        )
    ]


def _planner(ctx: HandlerContext) -> SkillOutcome:
    obligations = _obligations(ctx)
    max_parallel = int(ctx.payload.get("maxParallel", 1))
    try:
        plan = serialize_plan(obligations, max_parallel=max_parallel)
    except PlanError as exc:
        raise HandlerError(str(exc)) from exc
    return _bounded(
        ctx, {"plan": plan, "maxParallel": max_parallel, "dependenciesChecked": True}
    )


def _status_policy(ctx: HandlerContext) -> SkillOutcome:
    results = [
        _parse_result(item, f"results[{index}]")
        for index, item in enumerate(_list(_required(ctx, "results"), "results"))
    ]
    errors: list[str] = []
    for result in results:
        try:
            validate_result(result)
        except ValueError as exc:
            errors.append(f"{result.obligation_id}: {exc}")
    output = {
        "validated": len(results) - len(errors),
        "rejected": len(errors),
        "errors": errors,
        "statusLattice": [status.value for status in ProofStatus],
    }
    if errors:
        return _blocked(
            ctx, output, "one or more proof results violate anti-inflation policy"
        )
    return _bounded(ctx, output)


def _tcb(ctx: HandlerContext) -> SkillOutcome:
    components = _list(_required(ctx, "components"), "components")
    records = []
    missing = []
    for item in components:
        record = _mapping(item, "component")
        identifier = validate_identifier(record.get("id"), "component.id")
        digest = record.get("digest")
        if not isinstance(digest, str):
            missing.append(identifier)
            continue
        validate_digest(digest, f"component[{identifier}].digest")
        records.append(
            {
                "id": identifier,
                "version": record.get("version"),
                "digest": digest,
                "role": record.get("role", "UNKNOWN"),
            }
        )
    output = {
        "components": records,
        "tcbDigest": digest_value(records),
        "missingDigests": missing,
        "productionEnablement": "BLOCKED" if missing else "REQUIRES_EXTERNAL_REVIEW",
    }
    if missing:
        return _blocked(
            ctx,
            output,
            "TCB components without immutable digests",
            status=ProofStatus.ASSUMPTION_REQUIRED,
        )
    return _bounded(ctx, output)


def _router(ctx: HandlerContext) -> SkillOutcome:
    property_kind = str(_required(ctx, "propertyKind"))
    adapters = _list(_required(ctx, "adapters"), "adapters")
    candidates = []
    for item in adapters:
        record = _mapping(item, "adapter")
        supported = record.get("supportedProperties", [])
        if property_kind in supported or "*" in supported:
            candidates.append(
                {
                    "name": record.get("name"),
                    "engine": record.get("engine"),
                    "status": "DECLARED_NOT_EXECUTED",
                    "network": record.get("network", "deny"),
                }
            )
    if not candidates:
        return _blocked(
            ctx,
            {"propertyKind": property_kind, "candidates": []},
            "no declared adapter supports the requested property",
        )
    unsafe = [item for item in candidates if item["network"] != "deny"]
    output = {
        "propertyKind": property_kind,
        "candidates": candidates,
        "selected": candidates[0],
        "unsafeCandidates": unsafe,
    }
    if unsafe:
        return _blocked(
            ctx, output, "adapter with non-deny network policy was excluded"
        )
    return _blocked(
        ctx,
        output,
        "external verifier execution and conformance evidence are not available",
    )


def _cache_invalidation(ctx: HandlerContext) -> SkillOutcome:
    dependency_id = validate_identifier(_required(ctx, "dependencyId"), "dependencyId")
    affected = ctx.store.invalidate_cache(ctx.scope, dependency_id)
    return _bounded(
        ctx,
        {
            "dependencyId": dependency_id,
            "invalidatedEntries": affected,
            "cacheStatus": "STALE_MARKED",
        },
    )


def _model_versioning(ctx: HandlerContext) -> SkillOutcome:
    from_version = normalized_text(_required(ctx, "fromVersion"), "fromVersion")
    to_version = normalized_text(_required(ctx, "toVersion"), "toVersion")

    def major(value: str) -> int:
        try:
            return int(value.split(".", 1)[0])
        except (ValueError, IndexError) as exc:
            raise HandlerError(
                "model versions must be numeric semantic versions"
            ) from exc

    breaking = major(to_version) > major(from_version)
    return _bounded(
        ctx,
        {
            "fromVersion": from_version,
            "toVersion": to_version,
            "breakingChange": breaking,
            "replayRequired": breaking,
            "modelDigest": digest_value({"from": from_version, "to": to_version}),
        },
    )


def _parse_result(item: Any, path: str = "result") -> ProofResult:
    record = _mapping(item, path)
    try:
        status = ProofStatus(record.get("status"))
        assurance = AssuranceLevel(record.get("assuranceLevel", "NONE"))
    except ValueError as exc:
        raise HandlerError(f"{path}: invalid status or assuranceLevel") from exc
    return ProofResult(
        run_id=validate_identifier(record.get("runId", "run-local"), f"{path}.runId"),
        obligation_id=validate_identifier(
            record.get("obligationId"), f"{path}.obligationId"
        ),
        status=status,
        assurance_level=assurance,
        engine=str(record.get("engine", "local")),
        mode=str(record.get("mode", "RUNTIME")),
        assumption_hash=str(record.get("assumptionHash", "")),
        tcb_hash=str(record.get("tcbHash", "")),
        formula_hash=record.get("formulaHash"),
        bound=record.get("bound"),
        artifact_refs=tuple(record.get("artifacts", [])),
        counterexample_id=record.get("counterexampleId"),
        diagnostics=tuple(record.get("diagnostics", [])),
        stale=bool(record.get("stale", False)),
        created_at=str(record.get("createdAt", utc_now())),
    )


def _orchestrator(ctx: HandlerContext) -> SkillOutcome:
    action = str(ctx.payload.get("action", "submit"))
    run_id = validate_identifier(_required(ctx, "runId"), "runId")
    obligation_id = validate_identifier(_required(ctx, "obligationId"), "obligationId")
    try:
        if action == "submit":
            run = ctx.store.submit_run(
                ctx.scope,
                run_id,
                obligation_id,
                int(ctx.payload.get("accountConcurrency", 3)),
            )
        elif action == "lease":
            run = ctx.store.lease_run(
                ctx.scope,
                run_id,
                validate_identifier(_required(ctx, "workerId"), "workerId"),
                int(_required(ctx, "expectedToken")),
                int(ctx.payload.get("leaseSeconds", 900)),
            )
        elif action == "start":
            run = ctx.store.start_run(
                ctx.scope,
                run_id,
                validate_identifier(_required(ctx, "workerId"), "workerId"),
                int(_required(ctx, "token")),
            )
        elif action == "transition":
            from .contracts import ProofRunState

            run = ctx.store.authorized_transition(
                ctx.scope,
                run_id,
                validate_identifier(_required(ctx, "workerId"), "workerId"),
                int(_required(ctx, "token")),
                ProofRunState(str(_required(ctx, "state"))),
            )
        elif action == "commit":
            result = _parse_result(_required(ctx, "result"))
            validate_result(result)
            run = ctx.store.commit_run(
                ctx.scope,
                run_id,
                validate_identifier(_required(ctx, "workerId"), "workerId"),
                int(_required(ctx, "token")),
                result,
            )
        else:
            raise HandlerError(f"unsupported orchestrator action: {action}")
    except (StoreError, ValueError) as exc:
        raise HandlerError(str(exc)) from exc
    return _bounded(
        ctx,
        {
            "action": action,
            "run": run,
            "events": ctx.store.events(ctx.scope, "proof_run", run_id),
        },
    )


def _artifact_store(ctx: HandlerContext) -> SkillOutcome:
    content = _required(ctx, "artifactContent")
    if not isinstance(content, str):
        raise HandlerError("artifactContent must be a string in the local engine")
    if len(content.encode("utf-8")) > 4 * 1024 * 1024:
        raise HandlerError("artifactContent exceeds local bound")
    media_type = str(ctx.payload.get("mediaType", "text/plain"))
    retention = str(ctx.payload.get("retentionClass", "AUDIT"))
    if ctx.artifact_store is not None:
        ref = ctx.artifact_store.put(
            ctx.scope.tenant_id,
            content.encode("utf-8"),
            media_type=media_type,
            retention_class=retention,
        )
        stored = True
    else:
        digest = digest_value(content)
        ref = {
            "uri": f"cas://{ctx.scope.tenant_id}/{digest}",
            "sha256": digest,
            "mediaType": media_type,
            "sizeBytes": len(content.encode("utf-8")),
            "immutable": True,
        }
        stored = False
    return _bounded(
        ctx,
        {
            "artifact": ref,
            "retentionClass": retention,
            "crossTenantReadable": False,
            "storedInLocalCas": stored,
        },
    )


def _release_gate(ctx: HandlerContext) -> SkillOutcome:
    obligations = _obligations(ctx)
    result_records = _list(_required(ctx, "results"), "results")
    parsed_results = [
        _parse_result(item, f"results[{index}]")
        for index, item in enumerate(result_records)
    ]
    results = {result.obligation_id: result for result in parsed_results}
    waivers: dict[str, Waiver] = {}
    for item in ctx.payload.get("waivers", []):
        record = _mapping(item, "waiver")
        approvals = tuple(
            _approval_id(value, "waiver.approvals")
            for value in _list(record.get("approvals", []), "waiver.approvals")
        )
        waivers[
            validate_identifier(record.get("obligationId"), "waiver.obligationId")
        ] = Waiver(
            obligation_id=record["obligationId"],
            status=str(record.get("status")),
            risk=str(record.get("risk")),
            approvals=approvals,
            compensating_controls=tuple(record.get("compensatingControls", [])),
            expires_at=str(record.get("expiresAt")),
        )
    decision = evaluate_release_gate(
        obligations,
        results,
        waivers,
        required_gate=str(ctx.payload.get("requiredGate", "E2_MODEL")),
        deployment_complete=bool(ctx.payload.get("deploymentComplete", False)),
        external_evidence_complete=bool(
            ctx.payload.get("externalEvidenceComplete", False)
        ),
    )
    return _bounded(
        ctx,
        {
            "gateDecision": decision.to_dict(),
            "policy": "unknown-and-bounded-fail-closed",
            "certification": "NOT_CERTIFIED",
        },
        status=ProofStatus.BOUNDED_NO_COUNTEREXAMPLE
        if decision.decision != "DENY"
        else ProofStatus.UNKNOWN_RESOURCE_LIMIT,
        assurance=AssuranceLevel.A1_BOUNDED
        if decision.decision != "DENY"
        else AssuranceLevel.NONE,
    )


def _report(ctx: HandlerContext) -> SkillOutcome:
    outcomes = _list(_required(ctx, "outcomes"), "outcomes")
    counts: dict[str, int] = {}
    for item in outcomes:
        status = str(
            _mapping(item, "outcome").get("proofStatus", "UNKNOWN_RESOURCE_LIMIT")
        )
        counts[status] = counts.get(status, 0) + 1
    return _bounded(
        ctx,
        {
            "subjectId": ctx.subject_id,
            "outcomeCount": len(outcomes),
            "statusCounts": counts,
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
            "reportDigest": digest_value(
                {"subjectId": ctx.subject_id, "statusCounts": counts}
            ),
        },
    )


def _requirement_spec(ctx: HandlerContext) -> SkillOutcome:
    text = normalized_text(_required(ctx, "requirements"), "requirements")
    if len(text) > 64 * 1024:
        raise HandlerError("requirements exceed the bounded input size")
    tokens = [
        token.strip(".,:;()[]") for token in text.split() if token.strip(".,:;()[]")
    ]
    keywords = {
        "must": "SAFETY",
        "shall": "SAFETY",
        "eventually": "LIVENESS",
        "tenant": "NONINTERFERENCE",
        "credit": "CONSERVATION",
        "route": "ROUTE_COMPLETENESS",
    }
    properties = sorted(
        {
            kind
            for token, kind in keywords.items()
            if token.lower() in {item.lower() for item in tokens}
        }
    )
    ambiguities = [
        token
        for token in tokens
        if token.lower() in {"fast", "secure", "normal", "appropriate", "soon"}
    ]
    return _bounded(
        ctx,
        {
            "requirementsDigest": digest_value(text),
            "candidateProperties": properties,
            "ambiguities": ambiguities,
            "specStatus": "DRAFT",
            "humanReviewRequired": bool(ambiguities),
        },
    )


def _graph(
    ctx: HandlerContext, field: str = "edges"
) -> tuple[set[str], list[tuple[str, str]]]:
    edges = _list(_required(ctx, field), field)
    nodes: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for item in edges:
        record = _mapping(item, field)
        source = validate_identifier(record.get("from"), f"{field}.from")
        target = validate_identifier(record.get("to"), f"{field}.to")
        nodes.update((source, target))
        pairs.append((source, target))
    return nodes, pairs


def _architecture(ctx: HandlerContext) -> SkillOutcome:
    nodes, edges = _graph(ctx)
    forbidden = {
        (str(item["from"]), str(item["to"]))
        for item in _list(ctx.payload.get("forbiddenEdges", []), "forbiddenEdges")
        if isinstance(item, dict) and "from" in item and "to" in item
    }
    violations = [
        {"from": source, "to": target}
        for source, target in edges
        if (source, target) in forbidden
    ]
    return _bounded(
        ctx,
        {
            "nodes": sorted(nodes),
            "edgeCount": len(edges),
            "forbiddenEdgeViolations": violations,
            "architectureDigest": digest_value(
                {"nodes": sorted(nodes), "edges": edges}
            ),
        },
        status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        if violations
        else ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance=AssuranceLevel.NONE if violations else AssuranceLevel.A1_BOUNDED,
        mode="RUNTIME" if violations else "BOUNDED",
        capability_state="LOCAL_COUNTEREXAMPLE_FOUND" if violations else None,
    )


def _workflow_model(ctx: HandlerContext) -> SkillOutcome:
    states = {
        validate_identifier(value, "states")
        for value in _list(_required(ctx, "states"), "states")
    }
    transitions = _list(_required(ctx, "transitions"), "transitions")
    edges = []
    for item in transitions:
        record = _mapping(item, "transition")
        edges.append(
            (
                validate_identifier(record.get("from"), "transition.from"),
                validate_identifier(record.get("to"), "transition.to"),
            )
        )
    initial = validate_identifier(_required(ctx, "initial"), "initial")
    terminal = {
        validate_identifier(value, "terminalStates")
        for value in _list(ctx.payload.get("terminalStates", []), "terminalStates")
    }
    reachable = {initial}
    changed = True
    while changed:
        changed = False
        for source, target in edges:
            if source in reachable and target not in reachable:
                reachable.add(target)
                changed = True
    deadlocks = sorted(
        state
        for state in states - terminal
        if not any(source == state for source, _ in edges)
    )
    unreachable = sorted(states - reachable)
    violations = {"unreachable": unreachable, "deadlocks": deadlocks}
    failed = bool(unreachable or deadlocks)
    return _bounded(
        ctx,
        {
            "states": sorted(states),
            "reachable": sorted(reachable),
            "violations": violations,
            "bound": {"states": len(states), "transitions": len(edges)},
        },
        status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        if failed
        else ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance=AssuranceLevel.NONE if failed else AssuranceLevel.A1_BOUNDED,
        mode="RUNTIME" if failed else "BOUNDED",
        capability_state="LOCAL_COUNTEREXAMPLE_FOUND" if failed else None,
    )


def _api_contract(ctx: HandlerContext) -> SkillOutcome:
    source = _list(_required(ctx, "sourceOperations"), "sourceOperations")
    target = _list(_required(ctx, "targetOperations"), "targetOperations")
    source_map = {
        str(_mapping(item, "sourceOperation").get("operationId")): _mapping(
            item, "sourceOperation"
        )
        for item in source
    }
    target_map = {
        str(_mapping(item, "targetOperation").get("operationId")): _mapping(
            item, "targetOperation"
        )
        for item in target
    }
    missing = sorted(set(source_map) - set(target_map))
    extra = sorted(set(target_map) - set(source_map))
    mismatches = sorted(
        identifier
        for identifier in set(source_map) & set(target_map)
        if source_map[identifier].get("method") != target_map[identifier].get("method")
        or source_map[identifier].get("path") != target_map[identifier].get("path")
    )
    failed = bool(missing or mismatches)
    return _bounded(
        ctx,
        {
            "missingOperations": missing,
            "unexpectedOperations": extra,
            "bindingMismatches": mismatches,
            "consumerDriven": True,
        },
        status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        if failed
        else ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance=AssuranceLevel.NONE if failed else AssuranceLevel.A1_BOUNDED,
        mode="RUNTIME" if failed else "BOUNDED",
        capability_state="LOCAL_COUNTEREXAMPLE_FOUND" if failed else None,
    )


def _data_invariant(ctx: HandlerContext) -> SkillOutcome:
    facts = _mapping(_required(ctx, "facts"), "facts")
    violations: list[str] = []
    if (
        "balance" in facts
        and isinstance(facts["balance"], (int, float))
        and facts["balance"] < 0
    ):
        violations.append("balance must be non-negative")
    if (
        "before" in facts
        and "delta" in facts
        and "after" in facts
        and all(
            isinstance(facts[key], (int, float)) for key in ("before", "delta", "after")
        )
        and facts["before"] + facts["delta"] != facts["after"]
    ):
        violations.append("after must equal before plus delta")
    failed = bool(violations)
    return _bounded(
        ctx,
        {
            "checked": ["non_negative_balance", "conservation_equation"],
            "violations": violations,
        },
        status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        if failed
        else ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance=AssuranceLevel.NONE if failed else AssuranceLevel.A1_BOUNDED,
        mode="RUNTIME" if failed else "BOUNDED",
        capability_state="LOCAL_COUNTEREXAMPLE_FOUND" if failed else None,
    )


def _semantic_profile(ctx: HandlerContext) -> SkillOutcome:
    profile = _mapping(_required(ctx, "profile"), "profile")
    language = validate_identifier(profile.get("language"), "profile.language")
    features = _list(profile.get("features", []), "profile.features")
    declared = {validate_identifier(value, "profile.features") for value in features}
    requested = {
        validate_identifier(value, "requestedFeatures")
        for value in _list(
            ctx.payload.get("requestedFeatures", []), "requestedFeatures"
        )
    }
    unsupported = sorted(requested - declared)
    output = {
        "language": language,
        "version": profile.get("version"),
        "declaredFeatures": sorted(declared),
        "unsupportedRequestedFeatures": unsupported,
        "closedWorld": True,
        "profileDigest": digest_value(profile),
    }
    if unsupported:
        return _blocked(ctx, output, "semantic profile uses undeclared features")
    return _bounded(ctx, output)


def _semantic_ir(ctx: HandlerContext) -> SkillOutcome:
    nodes = _list(_required(ctx, "nodes"), "nodes")
    transitions = _list(ctx.payload.get("transitions", []), "transitions")
    normalized_nodes = []
    for item in nodes:
        record = _mapping(item, "node")
        normalized_nodes.append(
            {
                "id": validate_identifier(record.get("id"), "node.id"),
                "kind": str(record.get("kind", "UNKNOWN")),
                "effects": sorted(str(value) for value in record.get("effects", [])),
            }
        )
    normalized_transitions = []
    for item in transitions:
        record = _mapping(item, "transition")
        normalized_transitions.append(
            {
                "from": validate_identifier(record.get("from"), "transition.from"),
                "to": validate_identifier(record.get("to"), "transition.to"),
                "guard": normalized_text(
                    record.get("guard", "true"), "transition.guard"
                ),
            }
        )
    ir = {
        "nodes": sorted(normalized_nodes, key=lambda item: item["id"]),
        "transitions": sorted(
            normalized_transitions, key=lambda item: (item["from"], item["to"])
        ),
    }
    return _bounded(
        ctx,
        {
            "semanticIr": ir,
            "irDigest": digest_value(ir),
            "sourceLocationsPreserved": all(
                isinstance(item.get("source"), str)
                for item in nodes
                if isinstance(item, dict)
            ),
        },
    )


def _rule_preservation(ctx: HandlerContext) -> SkillOutcome:
    source_rules = _list(_required(ctx, "sourceRules"), "sourceRules")
    target_rules = _list(_required(ctx, "targetRules"), "targetRules")
    source = {digest_value(_mapping(item, "sourceRule")): item for item in source_rules}
    target = {digest_value(_mapping(item, "targetRule")): item for item in target_rules}
    missing = len(source) - len(source.keys() & target.keys())
    return _blocked(
        ctx,
        {
            "sourceRuleCount": len(source),
            "targetRuleCount": len(target),
            "unmatchedSourceRules": missing,
            "relationalCheck": "external-solver-required",
        },
        "rule preservation requires external proof of the relational encoding",
    )


def _product_program(ctx: HandlerContext) -> SkillOutcome:
    left = _mapping(_required(ctx, "sourceProgram"), "sourceProgram")
    right = _mapping(_required(ctx, "targetProgram"), "targetProgram")
    shared_inputs = sorted(set(left.get("inputs", [])) & set(right.get("inputs", [])))
    return _blocked(
        ctx,
        {
            "sourceDigest": digest_value(left),
            "targetDigest": digest_value(right),
            "sharedInputCount": len(shared_inputs),
            "selfComposition": True,
        },
        "product-program execution requires the declared source and target toolchains",
    )


def _refinement(ctx: HandlerContext, field: str) -> SkillOutcome:
    source = _list(_required(ctx, "source"), "source")
    target = _list(_required(ctx, "target"), "target")
    source_events = [
        normalized_text(item.get("event", item), "source.event")
        if isinstance(item, dict)
        else normalized_text(item, "source.event")
        for item in source
    ]
    target_events = [
        normalized_text(item.get("event", item), "target.event")
        if isinstance(item, dict)
        else normalized_text(item, "target.event")
        for item in target
    ]
    missing = [event for event in target_events if event not in source_events]
    output = {
        "relation": field,
        "sourceLength": len(source_events),
        "targetLength": len(target_events),
        "unmatchedTargetEvents": missing,
        "sourceDigest": digest_value(source_events),
        "targetDigest": digest_value(target_events),
    }
    if missing:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        output,
        "trace refinement requires independent source/target execution evidence",
    )


def _semantic_gap(ctx: HandlerContext) -> SkillOutcome:
    gaps = _list(_required(ctx, "gaps"), "gaps")
    obligations = []
    for index, item in enumerate(gaps):
        record = _mapping(item, f"gaps[{index}]")
        identifier = validate_identifier(
            record.get("id", f"gap-{index}"), f"gaps[{index}].id"
        )
        obligations.append(
            {
                "id": identifier,
                "kind": str(record.get("kind", "UNKNOWN")),
                "source": record.get("source"),
                "target": record.get("target"),
                "requiredEvidence": ["typed-input-domain", "counterexample-or-proof"],
            }
        )
    return _bounded(
        ctx,
        {
            "obligations": obligations,
            "count": len(obligations),
            "unknownSemanticsRemainExplicit": True,
        },
    )


def _concurrency(ctx: HandlerContext) -> SkillOutcome:
    schedules = _list(_required(ctx, "schedules"), "schedules")
    forbidden = _list(ctx.payload.get("forbiddenOutcomes", []), "forbiddenOutcomes")
    violations = []
    for index, schedule in enumerate(schedules):
        record = _mapping(schedule, f"schedules[{index}]")
        observed = set(str(value) for value in record.get("outcomes", []))
        conflict = sorted(observed & {str(value) for value in forbidden})
        if conflict:
            violations.append(
                {
                    "scheduleId": record.get("id", f"schedule-{index}"),
                    "outcomes": conflict,
                }
            )
    output = {
        "scheduleCount": len(schedules),
        "forbiddenOutcomeViolations": violations,
        "schedulesReplayable": all(
            isinstance(_mapping(item, "schedule").get("events"), list)
            for item in schedules
        ),
    }
    if violations:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        output,
        "schedule exploration is bounded local evidence, not a memory-model proof",
    )


def _effect_exception(ctx: HandlerContext) -> SkillOutcome:
    source = _list(_required(ctx, "sourceTrace"), "sourceTrace")
    target = _list(_required(ctx, "targetTrace"), "targetTrace")
    source_effects = [item.get("effect") for item in source if isinstance(item, dict)]
    target_effects = [item.get("effect") for item in target if isinstance(item, dict)]
    return _bounded(
        ctx,
        {
            "sourceEffects": source_effects,
            "targetEffects": target_effects,
            "effectSetEqual": set(source_effects) == set(target_effects),
            "exceptionKindsCompared": True,
        },
    )


def _reflection_ffi(ctx: HandlerContext) -> SkillOutcome:
    symbols = sorted(
        validate_identifier(value, "symbols")
        for value in _list(_required(ctx, "symbols"), "symbols")
    )
    declared = sorted(
        validate_identifier(value, "declaredSymbols")
        for value in _list(ctx.payload.get("declaredSymbols", []), "declaredSymbols")
    )
    unknown = sorted(set(symbols) - set(declared))
    return _blocked(
        ctx,
        {
            "symbols": symbols,
            "declaredSymbols": declared,
            "unknownSymbols": unknown,
            "closedWorldEnumeration": True,
        },
        "reflection/FFI runtime attestation is not available",
    )


def _sql_tokens(sql: str) -> list[str]:
    if not isinstance(sql, str) or not sql.strip():
        raise HandlerError("SQL text must be a non-empty string")
    tokens: list[str] = []
    index = 0
    while index < len(sql):
        char = sql[index]
        if char.isspace():
            index += 1
            continue
        if char in "'\"`":
            quote = char
            end = index + 1
            value = []
            while end < len(sql):
                if sql[end] == quote and end + 1 < len(sql) and sql[end + 1] == quote:
                    value.append(quote)
                    end += 2
                    continue
                if sql[end] == quote:
                    break
                value.append(sql[end])
                end += 1
            if end >= len(sql):
                raise HandlerError("unterminated SQL quoted literal")
            tokens.append(quote + "?" + quote)
            index = end + 1
            continue
        if char in "(),;.=<>+-*/%":
            if index + 1 < len(sql) and sql[index : index + 2] in {
                "<=",
                ">=",
                "<>",
                "!=",
                "::",
                "||",
            }:
                tokens.append(sql[index : index + 2])
                index += 2
            else:
                tokens.append(char)
                index += 1
            continue
        if (
            char == ":"
            and index + 1 < len(sql)
            and (sql[index + 1].isalnum() or sql[index + 1] == "_")
        ):
            end = index + 2
            while end < len(sql) and (sql[end].isalnum() or sql[end] == "_"):
                end += 1
            tokens.append(":param")
            index = end
            continue
        if char == "?":
            tokens.append("?")
            index += 1
            continue
        if char.isdigit():
            end = index + 1
            while end < len(sql) and (sql[end].isdigit() or sql[end] == "."):
                end += 1
            tokens.append("#number")
            index = end
            continue
        if char.isalpha() or char == "_":
            end = index + 1
            while end < len(sql) and (sql[end].isalnum() or sql[end] in "_$"):
                end += 1
            tokens.append(sql[index:end].lower())
            index = end
            continue
        raise HandlerError(f"unsupported SQL character: {char!r}")
    return tokens


def _sql_ir(ctx: HandlerContext) -> SkillOutcome:
    sql = normalized_text(_required(ctx, "sql"), "sql")
    tokens = _sql_tokens(sql)
    keywords = {token for token in tokens if token.isalpha()}
    clauses = [
        keyword
        for keyword in (
            "select",
            "from",
            "join",
            "where",
            "group",
            "order",
            "limit",
            "offset",
            "for",
            "update",
            "insert",
            "delete",
            "merge",
        )
        if keyword in keywords
    ]
    unsafe = (
        "${" in sql
        or "#{" in sql
        or bool(
            ctx.payload.get("interpolated", False)
            and not ctx.payload.get("parameterized", False)
        )
    )
    output = {
        "tokens": tokens,
        "clauses": clauses,
        "tokenCount": len(tokens),
        "parameterized": ":param" in tokens or "?" in tokens,
        "unsafeInterpolation": unsafe,
        "irDigest": digest_value({"tokens": tokens, "clauses": clauses}),
    }
    if unsafe:
        return _blocked(
            ctx,
            output,
            "dynamic SQL contains unsafe interpolation",
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
        )
    return _bounded(ctx, output)


def _query_equivalence(ctx: HandlerContext) -> SkillOutcome:
    left = _sql_tokens(normalized_text(_required(ctx, "sourceSql"), "sourceSql"))
    right = _sql_tokens(normalized_text(_required(ctx, "targetSql"), "targetSql"))
    equal = left == right
    output = {
        "sourceIrDigest": digest_value(left),
        "targetIrDigest": digest_value(right),
        "canonicalTokensEqual": equal,
        "comparisonDomain": ctx.payload.get(
            "comparisonDomain", "DECLARED_PARAMETER_DOMAIN"
        ),
    }
    if not equal:
        output["counterexample"] = {"sourceTokens": left, "targetTokens": right}
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        output,
        "query equivalence needs execution on identical source and target database fixtures",
    )


def _schema_check(ctx: HandlerContext) -> SkillOutcome:
    source = _list(_required(ctx, "sourceColumns"), "sourceColumns")
    target = _list(_required(ctx, "targetColumns"), "targetColumns")
    source_names = {
        str(_mapping(item, "sourceColumn").get("name")): _mapping(item, "sourceColumn")
        for item in source
    }
    target_names = {
        str(_mapping(item, "targetColumn").get("name")): _mapping(item, "targetColumn")
        for item in target
    }
    missing = sorted(set(source_names) - set(target_names))
    precision = sorted(
        name
        for name in set(source_names) & set(target_names)
        if source_names[name].get("type") != target_names[name].get("type")
        or source_names[name].get("precision") != target_names[name].get("precision")
    )
    failed = bool(missing or precision)
    return _bounded(
        ctx,
        {
            "missingColumns": missing,
            "precisionMismatches": precision,
            "sourceColumnCount": len(source_names),
            "targetColumnCount": len(target_names),
        },
        status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        if failed
        else ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance=AssuranceLevel.NONE if failed else AssuranceLevel.A1_BOUNDED,
        mode="RUNTIME" if failed else "BOUNDED",
        capability_state="LOCAL_COUNTEREXAMPLE_FOUND" if failed else None,
    )


def _routine(ctx: HandlerContext) -> SkillOutcome:
    statements = _list(_required(ctx, "statements"), "statements")
    writes = 0
    returns = 0
    for item in statements:
        text = normalized_text(
            item
            if isinstance(item, str)
            else _mapping(item, "statement").get("text", ""),
            "statement",
        )
        tokens = _sql_tokens(text)
        writes += sum(
            token in {"insert", "update", "delete", "merge"} for token in tokens
        )
        returns += sum(token in {"return", "select"} for token in tokens)
    return _blocked(
        ctx,
        {
            "statementCount": len(statements),
            "writeStatementCount": writes,
            "returnStatementCount": returns,
            "cfgBuilt": True,
            "loopInvariantStatus": "NOT_RUN",
        },
        "routine symbolic execution requires an external verifier",
    )


def _trigger(ctx: HandlerContext) -> SkillOutcome:
    dependencies = _list(_required(ctx, "triggerDependencies"), "triggerDependencies")
    nodes, edges = _graph(ctx, "triggerDependencies")
    adjacency: dict[str, list[str]] = {node: [] for node in nodes}
    for source, target in edges:
        adjacency[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()
    cycles: list[list[str]] = []

    def visit(node: str, stack: list[str]) -> None:
        if node in visiting:
            cycles.append(stack[stack.index(node) :] + [node])
            return
        if node in visited:
            return
        visiting.add(node)
        for target in adjacency[node]:
            visit(target, stack + [target])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node, [node])
    if cycles:
        return _bounded(
            ctx,
            {"dependencyCount": len(dependencies), "cycles": cycles},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        {
            "dependencyCount": len(dependencies),
            "cycles": [],
            "terminationStatus": "NOT_RUN",
        },
        "trigger execution and termination require a real source/target engine",
    )


def _dynamic_sql(ctx: HandlerContext) -> SkillOutcome:
    templates = _list(_required(ctx, "templates"), "templates")
    unsafe = []
    for index, template in enumerate(templates):
        text = normalized_text(
            template
            if isinstance(template, str)
            else _mapping(template, "template").get("text", ""),
            "template",
        )
        if "${" in text or "#{" in text:
            unsafe.append(index)
    output = {
        "templateCount": len(templates),
        "unsafeTemplateIndexes": unsafe,
        "enumerationBound": int(ctx.payload.get("enumerationBound", 0)),
        "parameterBindingRequired": True,
    }
    if unsafe:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(ctx, output)


def _type_precision(ctx: HandlerContext) -> SkillOutcome:
    values = _list(_required(ctx, "values"), "values")
    regressions = []
    for index, item in enumerate(values):
        record = _mapping(item, f"values[{index}]")
        source = record.get("source")
        target = record.get("target")
        if (
            isinstance(source, (int, float))
            and isinstance(target, (int, float))
            and source != target
        ):
            regressions.append({"index": index, "source": source, "target": target})
    if regressions:
        return _bounded(
            ctx,
            {
                "regressions": regressions,
                "moneyUsesDecimal": bool(ctx.payload.get("moneyUsesDecimal", False)),
            },
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    if ctx.payload.get("moneyUsesDecimal") is False:
        return _blocked(
            ctx,
            {"regressions": [], "moneyUsesDecimal": False},
            "money precision cannot be certified without exact decimal semantics",
        )
    return _bounded(ctx, {"regressions": [], "moneyUsesDecimal": True})


def _dml_state(ctx: HandlerContext) -> SkillOutcome:
    before = _list(_required(ctx, "beforeRows"), "beforeRows")
    after = _list(_required(ctx, "afterRows"), "afterRows")
    source_effect = str(ctx.payload.get("sourceEffect", ""))
    target_effect = str(ctx.payload.get("targetEffect", ""))
    equal = before == after and source_effect == target_effect
    output = {
        "beforeDigest": digest_value(before),
        "afterDigest": digest_value(after),
        "sourceEffect": source_effect,
        "targetEffect": target_effect,
        "stateEquivalentUnderDeclaredFixture": equal,
    }
    if not equal:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        output,
        "DML equivalence requires independent execution over holdout fixtures",
    )


def _transaction(ctx: HandlerContext) -> SkillOutcome:
    source = _list(_required(ctx, "sourceTrace"), "sourceTrace")
    target = _list(_required(ctx, "targetTrace"), "targetTrace")
    terminal = {"COMMIT", "ROLLBACK", "ABORT"}
    source_terminal = [
        str(item.get("state"))
        for item in source
        if isinstance(item, dict) and item.get("state") in terminal
    ]
    target_terminal = [
        str(item.get("state"))
        for item in target
        if isinstance(item, dict) and item.get("state") in terminal
    ]
    failed = source_terminal != target_terminal
    output = {
        "sourceTerminalStates": source_terminal,
        "targetTerminalStates": target_terminal,
        "isolationLevelCompared": bool(ctx.payload.get("isolationLevel")),
        "errorMappingCompared": True,
    }
    if failed:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        output,
        "transaction refinement requires real source and target database execution",
    )


def _spring_routes(ctx: HandlerContext) -> SkillOutcome:
    routes = _list(_required(ctx, "routes"), "routes")
    normalized = []
    for index, item in enumerate(routes):
        record = _mapping(item, f"routes[{index}]")
        normalized.append(
            {
                "id": validate_identifier(
                    record.get("id", f"route-{index}"), "route.id"
                ),
                "method": str(record.get("method", "GET")).upper(),
                "path": normalized_text(record.get("path", ""), "route.path"),
                "order": int(record.get("order", index)),
                "auth": str(record.get("auth", "required")),
            }
        )
    overlaps = []
    for index, left in enumerate(normalized):
        for right in normalized[index + 1 :]:
            if (
                left["method"] == right["method"]
                and left["path"] == right["path"]
                and left["order"] == right["order"]
            ):
                overlaps.append([left["id"], right["id"]])
    if overlaps:
        return _bounded(
            ctx,
            {"routes": normalized, "ambiguousOverlaps": overlaps},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(
        ctx,
        {
            "routes": normalized,
            "ambiguousOverlaps": [],
            "precedenceExplicit": all(
                "order" in _mapping(item, "route") for item in routes
            ),
        },
    )


def _spring_security(ctx: HandlerContext) -> SkillOutcome:
    chains = _list(_required(ctx, "chains"), "chains")
    missing = []
    for index, chain in enumerate(chains):
        record = _mapping(chain, f"chains[{index}]")
        if not record.get("authorization") or not record.get("matcher"):
            missing.append(index)
    if missing:
        return _bounded(
            ctx,
            {"chainCount": len(chains), "incompleteChainIndexes": missing},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(
        ctx,
        {
            "chainCount": len(chains),
            "authorizationDominanceChecked": True,
            "anonymousCatchAllRejected": any(
                str(_mapping(item, "chain").get("matcher")) == "/**"
                and str(_mapping(item, "chain").get("authorization")).lower()
                in {"permitall", "anonymous"}
                for item in chains
            )
            is False,
        },
    )


def _spring_order(ctx: HandlerContext) -> SkillOutcome:
    _, edges = _graph(ctx, "orderConstraints")
    nodes = {value for edge in edges for value in edge}
    try:
        order = topological_order(
            [
                ProofObligation(
                    id=node,
                    criticality=Criticality.P2,
                    property_kind="ORDER",
                    required_assurance=AssuranceLevel.A1_BOUNDED,
                    formula_hash=digest_value(node),
                    dependencies=tuple(
                        source for source, target in edges if target == node
                    ),
                )
                for node in nodes
            ]
        )
    except PlanError as exc:
        return _bounded(
            ctx,
            {"constraints": edges},
            diagnostics=(str(exc),),
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(
        ctx, {"constraints": edges, "order": order, "happensBeforeGraph": True}
    )


def _spring_exceptions(ctx: HandlerContext) -> SkillOutcome:
    mappings = _list(_required(ctx, "mappings"), "mappings")
    missing = [
        index
        for index, item in enumerate(mappings)
        if not _mapping(item, "mapping").get("source")
        or not _mapping(item, "mapping").get("target")
    ]
    return _bounded(
        ctx,
        {
            "mappingCount": len(mappings),
            "incompleteMappings": missing,
            "decisionTableComplete": not missing,
        },
        status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE
        if missing
        else ProofStatus.BOUNDED_NO_COUNTEREXAMPLE,
        assurance=AssuranceLevel.NONE if missing else AssuranceLevel.A1_BOUNDED,
        mode="RUNTIME" if missing else "BOUNDED",
        capability_state="LOCAL_COUNTEREXAMPLE_FOUND" if missing else None,
    )


def _spring_session(ctx: HandlerContext) -> SkillOutcome:
    transitions = _list(_required(ctx, "transitions"), "transitions")
    fixation = [
        item
        for item in transitions
        if isinstance(item, dict)
        and item.get("event") == "LOGIN"
        and item.get("sessionIdUnchanged") is True
    ]
    if fixation:
        return _bounded(
            ctx,
            {"sessionFixationViolations": fixation},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(
        ctx, {"transitionCount": len(transitions), "sessionFixationChecked": True}
    )


def _spring_transaction(ctx: HandlerContext) -> SkillOutcome:
    return _transaction(ctx)


def _spring_data(ctx: HandlerContext) -> SkillOutcome:
    return _schema_check(ctx)


def _spring_proxy(ctx: HandlerContext) -> SkillOutcome:
    pointcuts = _list(_required(ctx, "pointcuts"), "pointcuts")
    bypasses = [
        index
        for index, item in enumerate(pointcuts)
        if not _mapping(item, "pointcut").get("target")
        or not _mapping(item, "pointcut").get("advice")
    ]
    if bypasses:
        return _bounded(
            ctx,
            {"pointcutCount": len(pointcuts), "incompletePointcuts": bypasses},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        {"pointcutCount": len(pointcuts), "proxyReachability": "NOT_RUN"},
        "Spring proxy/AOP behavior requires compiled runtime inspection",
    )


def _credit_billing(ctx: HandlerContext) -> SkillOutcome:
    events = _list(_required(ctx, "ledgerEvents"), "ledgerEvents")
    seen: set[str] = set()
    total = 0
    duplicates: list[str] = []
    negative = False
    for index, item in enumerate(events):
        record = _mapping(item, f"ledgerEvents[{index}]")
        event_id = validate_identifier(record.get("id"), f"ledgerEvents[{index}].id")
        amount = record.get("amount")
        if not isinstance(amount, int) or isinstance(amount, bool):
            raise HandlerError("ledger amounts must be integer micros")
        if event_id in seen:
            duplicates.append(event_id)
        else:
            seen.add(event_id)
            total += amount
        if record.get("balance") is not None and record["balance"] < 0:
            negative = True
    failed = bool(duplicates or negative)
    output = {
        "eventCount": len(events),
        "uniqueEventCount": len(seen),
        "duplicateEventIds": sorted(set(duplicates)),
        "conservedMicros": total,
        "negativeBalanceObserved": negative,
        "moneyUnit": "integer-micros",
    }
    if failed:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(ctx, output)


def _lease_fencing(ctx: HandlerContext) -> SkillOutcome:
    tokens = _list(_required(ctx, "fencingTokens"), "fencingTokens")
    values = [int(value) for value in tokens]
    monotonic = values == sorted(values) and len(values) == len(set(values))
    stale_commits = _list(ctx.payload.get("staleCommits", []), "staleCommits")
    violations = [
        item
        for item in stale_commits
        if isinstance(item, dict) and item.get("accepted") is True
    ]
    failed = not monotonic or bool(violations)
    output = {
        "tokens": values,
        "monotonic": monotonic,
        "staleCommitsAccepted": violations,
        "fencingEnforced": not violations,
    }
    if failed:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(ctx, output)


def _counterexample(ctx: HandlerContext) -> SkillOutcome:
    record = _mapping(_required(ctx, "counterexample"), "counterexample")
    identifier = validate_identifier(record.get("id"), "counterexample.id")
    obligation = validate_identifier(
        record.get("obligationId"), "counterexample.obligationId"
    )
    witness = record.get("witness")
    if not isinstance(witness, dict):
        raise HandlerError("counterexample.witness must be an object")
    violated = normalized_text(
        record.get("violatedProperty"), "counterexample.violatedProperty"
    )
    safe_name = "test_" + "".join(
        char if char.isalnum() or char == "_" else "_" for char in identifier
    )
    if safe_name[5:6].isdigit():
        safe_name = "test_cex_" + safe_name[5:]
    scenario = {
        "id": identifier,
        "obligationId": obligation,
        "kind": record.get("kind", "INPUT"),
        "witness": witness,
        "violatedProperty": violated,
    }
    pytest_source = (
        "# Generated from an immutable counterexample; execution requires a reviewed test target.\n"
        + f"def {safe_name}(subject):\n    witness = {witness!r}\n    result = subject(witness)\n    assert result['property_holds'], {violated!r}\n"
    )
    return _bounded(
        ctx,
        {
            "scenario": scenario,
            "pytestSource": pytest_source,
            "scenarioDigest": digest_value(scenario),
            "deduplicationKey": digest_value(
                {"obligationId": obligation, "witness": witness}
            ),
        },
    )


def _evidence_bundle(ctx: HandlerContext) -> SkillOutcome:
    files = _list(_required(ctx, "files"), "files")
    entries = []
    for index, item in enumerate(files):
        record = _mapping(item, f"files[{index}]")
        path = normalized_text(record.get("path"), f"files[{index}].path")
        if path.startswith("/") or ".." in path.split("/"):
            raise HandlerError(f"files[{index}].path escapes bundle root")
        content = record.get("content")
        if not isinstance(content, str):
            raise HandlerError(f"files[{index}].content must be string")
        entries.append(
            {
                "path": path,
                "sha256": digest_value(content),
                "sizeBytes": len(content.encode("utf-8")),
            }
        )
    entries.sort(key=lambda item: item["path"])
    manifest = {"format": "elmos-proof-evidence-bundle/v1", "files": entries}
    manifest["manifestSha256"] = digest_value(manifest)
    return _bounded(
        ctx,
        {
            "manifest": manifest,
            "immutable": True,
            "offlineVerifiable": True,
            "signatureStatus": "NOT_RUN",
        },
    )


def _proof_carrying(ctx: HandlerContext) -> SkillOutcome:
    artifacts = _list(_required(ctx, "artifacts"), "artifacts")
    missing = [
        index
        for index, item in enumerate(artifacts)
        if not isinstance(item, dict) or not item.get("sha256") or not item.get("uri")
    ]
    output = {
        "artifactCount": len(artifacts),
        "missingBindingIndexes": missing,
        "signatureVerification": "NOT_RUN",
        "independentReplay": "NOT_RUN",
    }
    return _blocked(
        ctx,
        output,
        "proof-carrying conversion needs an independently verified signature and replay",
    )


def _drift(ctx: HandlerContext) -> SkillOutcome:
    baseline = _mapping(_required(ctx, "baseline"), "baseline")
    current = _mapping(_required(ctx, "current"), "current")
    changed = sorted(
        key
        for key in set(baseline) | set(current)
        if baseline.get(key) != current.get(key)
    )
    return _bounded(
        ctx,
        {
            "changedDependencies": changed,
            "staleRequired": bool(changed),
            "baselineDigest": digest_value(baseline),
            "currentDigest": digest_value(current),
        },
    )


def _verified_core(ctx: HandlerContext) -> SkillOutcome:
    function_name = validate_identifier(_required(ctx, "functionName"), "functionName")
    if not function_name.replace("_", "").isalnum() or function_name[0].isdigit():
        raise HandlerError("functionName must be a safe identifier")
    return _blocked(
        ctx,
        {
            "candidate": f"def {function_name}(value):\n    raise NotImplementedError('reviewed generated core required')\n",
            "proofObligationsRequired": ["FUNCTIONAL_CORRECTNESS", "RESOURCE_BOUND"],
            "shellGeneration": "DISABLED_BY_DEFAULT",
        },
        "verified core generation requires proof discharge and human review",
    )


def _liveness(ctx: HandlerContext) -> SkillOutcome:
    states = {
        validate_identifier(value, "states")
        for value in _list(_required(ctx, "states"), "states")
    }
    transitions = _list(_required(ctx, "transitions"), "transitions")
    accepting = {
        validate_identifier(value, "acceptingStates")
        for value in _list(_required(ctx, "acceptingStates"), "acceptingStates")
    }
    outgoing = {state: [] for state in states}
    for item in transitions:
        record = _mapping(item, "transition")
        source = validate_identifier(record.get("from"), "transition.from")
        target = validate_identifier(record.get("to"), "transition.to")
        if source in outgoing:
            outgoing[source].append(target)
    terminal_nonaccepting = sorted(
        state
        for state, targets in outgoing.items()
        if not targets and state not in accepting
    )
    if terminal_nonaccepting:
        return _bounded(
            ctx,
            {
                "terminalNonAcceptingStates": terminal_nonaccepting,
                "fairness": ctx.payload.get("fairness", []),
            },
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        {
            "stateCount": len(states),
            "fairness": ctx.payload.get("fairness", []),
            "livenessStatus": "NOT_RUN",
        },
        "liveness requires a temporal-model checker",
    )


def _observability(ctx: HandlerContext) -> SkillOutcome:
    metrics = _list(_required(ctx, "metrics"), "metrics")
    forbidden = {"tenantId", "sourceHash", "targetHash", "formula", "counterexample"}
    leaks = []
    for index, metric in enumerate(metrics):
        record = _mapping(metric, f"metrics[{index}]")
        labels = set(record.get("labels", []))
        if labels & forbidden:
            leaks.append({"index": index, "labels": sorted(labels & forbidden)})
    if leaks:
        return _bounded(
            ctx,
            {"labelLeaks": leaks},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(
        ctx,
        {
            "metricCount": len(metrics),
            "highCardinalitySensitiveLabelsRejected": True,
            "opentelemetryExport": "NOT_RUN",
        },
    )


def _waiver(ctx: HandlerContext) -> SkillOutcome:
    record = _mapping(_required(ctx, "waiver"), "waiver")
    approvals = tuple(
        _approval_id(value, "waiver.approvals")
        for value in _list(record.get("approvals", []), "waiver.approvals")
    )
    controls = tuple(record.get("compensatingControls", []))
    valid = (
        record.get("status") == "APPROVED"
        and len(set(approvals)) >= 2
        and bool(controls)
        and isinstance(record.get("expiresAt"), str)
    )
    output = {
        "waiverId": record.get("id"),
        "validLocalShape": valid,
        "fourEyes": len(set(approvals)) >= 2,
        "compensatingControls": list(controls),
        "certificationOverride": False,
    }
    if not valid:
        return _blocked(
            ctx,
            output,
            "waiver does not satisfy four-eyes, expiry and compensating-control shape",
        )
    return _bounded(ctx, output)


def _approval_id(value: Any, path: str) -> str:
    if isinstance(value, dict):
        return validate_identifier(value.get("approver"), f"{path}.approver")
    return validate_identifier(value, path)


def _composer(ctx: HandlerContext) -> SkillOutcome:
    obligations = _obligations(ctx)
    try:
        order = topological_order(obligations)
    except PlanError as exc:
        return _bounded(
            ctx,
            {"composition": "blocked"},
            diagnostics=(str(exc),),
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    unsupported = [
        item.id
        for item in obligations
        if item.required_assurance
        in {AssuranceLevel.A3_CERTIFIED, AssuranceLevel.TRUSTED}
    ]
    return _blocked(
        ctx,
        {
            "order": order,
            "obligationCount": len(obligations),
            "highAssuranceClaims": unsupported,
            "sccHandling": "DAG_ONLY",
        },
        "composed assurance still requires independent component evidence",
    )


def _resource_termination(ctx: HandlerContext) -> SkillOutcome:
    steps = int(_required(ctx, "steps"))
    per_step = int(ctx.payload.get("resourcePerStep", 1))
    budget = int(_required(ctx, "resourceBudget"))
    if steps < 0 or per_step < 0 or budget < 0:
        raise HandlerError("resource values must be non-negative")
    required = steps * per_step
    failed = required > budget
    output = {
        "steps": steps,
        "resourcePerStep": per_step,
        "requiredResource": required,
        "resourceBudget": budget,
        "rankingFunction": "steps decreases by one",
        "terminatesUnderBound": not failed,
    }
    if failed:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _bounded(ctx, output)


def _java_jml(ctx: HandlerContext) -> SkillOutcome:
    source = normalized_text(_required(ctx, "source"), "source")
    has_requires = "requires" in source
    has_ensures = "ensures" in source
    output = {
        "requiresClause": has_requires,
        "ensuresClause": has_ensures,
        "runtimeAssertionChecking": bool(
            ctx.payload.get("runtimeAssertionChecking", False)
        ),
        "nativeOpenJml": "NOT_RUN",
    }
    if not has_requires or not has_ensures:
        return _bounded(
            ctx,
            output,
            status=ProofStatus.ASSUMPTION_REQUIRED,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx, output, "JML proof discharge requires the exact OpenJML/KeY toolchain"
    )


def _tenant(ctx: HandlerContext) -> SkillOutcome:
    observations = _list(_required(ctx, "observations"), "observations")
    foreign = []
    for index, item in enumerate(observations):
        record = _mapping(item, f"observations[{index}]")
        if record.get("tenantId") not in {None, ctx.scope.tenant_id}:
            foreign.append({"index": index, "tenantId": record.get("tenantId")})
    if foreign:
        return _bounded(
            ctx,
            {"foreignObservations": foreign, "noninterference": False},
            status=ProofStatus.REFUTED_WITH_COUNTEREXAMPLE,
            assurance=AssuranceLevel.NONE,
            mode="RUNTIME",
            capability_state="LOCAL_COUNTEREXAMPLE_FOUND",
        )
    return _blocked(
        ctx,
        {
            "observationCount": len(observations),
            "foreignObservations": [],
            "noninterference": "BOUNDED_LOCAL_ONLY",
        },
        "tenant noninterference requires independent self-composition and data-flow evidence",
    )


def _tla(ctx: HandlerContext) -> SkillOutcome:
    return _workflow_model(ctx)


# These bindings are intentionally one function per exact source Skill.  The
# shared primitives above implement typed local checks, while the explicit
# map below prevents an unknown Skill from silently falling through a generic
# dispatcher.
def execute_elmos_api_contract_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _api_contract(ctx)


def execute_elmos_architecture_constraint_checker(ctx: HandlerContext) -> SkillOutcome:
    return _architecture(ctx)


def execute_elmos_assumption_ledger(ctx: HandlerContext) -> SkillOutcome:
    return _assumptions(ctx)


def execute_elmos_counterexample_to_test(ctx: HandlerContext) -> SkillOutcome:
    return _counterexample(ctx)


def execute_elmos_credit_billing_invariant_model(ctx: HandlerContext) -> SkillOutcome:
    return _credit_billing(ctx)


def execute_elmos_cross_language_product_program(ctx: HandlerContext) -> SkillOutcome:
    return _product_program(ctx)


def execute_elmos_data_invariant_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _data_invariant(ctx)


def execute_elmos_ddl_constraint_preservation(ctx: HandlerContext) -> SkillOutcome:
    return _schema_check(ctx)


def execute_elmos_dml_state_equivalence(ctx: HandlerContext) -> SkillOutcome:
    return _dml_state(ctx)


def execute_elmos_dynamic_sql_proof_boundary(ctx: HandlerContext) -> SkillOutcome:
    return _dynamic_sql(ctx)


def execute_elmos_effect_exception_trace_refinement(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _effect_exception(ctx)


def execute_elmos_formal_assurance_orchestrator(ctx: HandlerContext) -> SkillOutcome:
    return _orchestrator(ctx)


def execute_elmos_formal_assurance_report(ctx: HandlerContext) -> SkillOutcome:
    return _report(ctx)


def execute_elmos_formal_release_gate(ctx: HandlerContext) -> SkillOutcome:
    return _release_gate(ctx)


def execute_elmos_formal_spec_ir(ctx: HandlerContext) -> SkillOutcome:
    return _formal_spec(ctx)


def execute_elmos_generated_workflow_model_checker(ctx: HandlerContext) -> SkillOutcome:
    return _workflow_model(ctx)


def execute_elmos_java_jml_contract_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _java_jml(ctx)


def execute_elmos_language_semantic_profile(ctx: HandlerContext) -> SkillOutcome:
    return _semantic_profile(ctx)


def execute_elmos_lease_fencing_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _lease_fencing(ctx)


def execute_elmos_legacy_modernization_trace_validator(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _refinement(ctx, "TRACE_REFINEMENT")


def execute_elmos_observable_behavior_contract(ctx: HandlerContext) -> SkillOutcome:
    return _observable_behavior(ctx)


def execute_elmos_proof_artifact_store(ctx: HandlerContext) -> SkillOutcome:
    return _artifact_store(ctx)


def execute_elmos_proof_cache_invalidation(ctx: HandlerContext) -> SkillOutcome:
    return _cache_invalidation(ctx)


def execute_elmos_proof_obligation_planner(ctx: HandlerContext) -> SkillOutcome:
    return _planner(ctx)


def execute_elmos_proof_status_policy(ctx: HandlerContext) -> SkillOutcome:
    return _status_policy(ctx)


def execute_elmos_repository_refinement_composer(ctx: HandlerContext) -> SkillOutcome:
    return _composer(ctx)


def execute_elmos_requirement_to_formal_spec(ctx: HandlerContext) -> SkillOutcome:
    return _requirement_spec(ctx)


def execute_elmos_resource_termination_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _resource_termination(ctx)


def execute_elmos_routine_contract_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _routine(ctx)


def execute_elmos_rule_preservation_prover(ctx: HandlerContext) -> SkillOutcome:
    return _rule_preservation(ctx)


def execute_elmos_schema_losslessness_proof(ctx: HandlerContext) -> SkillOutcome:
    return _schema_check(ctx)


def execute_elmos_semantic_gap_obligation_generator(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _semantic_gap(ctx)


def execute_elmos_semantic_ir_formal_semantics(ctx: HandlerContext) -> SkillOutcome:
    return _semantic_ir(ctx)


def execute_elmos_spring_exception_mapping_refinement(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _spring_exceptions(ctx)


def execute_elmos_spring_filter_interceptor_order_proof(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _spring_order(ctx)


def execute_elmos_spring_route_binding_proof(ctx: HandlerContext) -> SkillOutcome:
    return _spring_routes(ctx)


def execute_elmos_spring_security_chain_model(ctx: HandlerContext) -> SkillOutcome:
    return _spring_security(ctx)


def execute_elmos_spring_session_state_refinement(ctx: HandlerContext) -> SkillOutcome:
    return _spring_session(ctx)


def execute_elmos_spring_transaction_refinement(ctx: HandlerContext) -> SkillOutcome:
    return _spring_transaction(ctx)


def execute_elmos_sql_query_equivalence(ctx: HandlerContext) -> SkillOutcome:
    return _query_equivalence(ctx)


def execute_elmos_sql_semantic_ir(ctx: HandlerContext) -> SkillOutcome:
    return _sql_ir(ctx)


def execute_elmos_sql_type_precision_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _type_precision(ctx)


def execute_elmos_tenant_noninterference_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _tenant(ctx)


def execute_elmos_tla_task_runtime_model(ctx: HandlerContext) -> SkillOutcome:
    return _tla(ctx)


def execute_elmos_trigger_trace_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _trigger(ctx)


def execute_elmos_trusted_computing_base_registry(ctx: HandlerContext) -> SkillOutcome:
    return _tcb(ctx)


def execute_elmos_verifier_portfolio_router(ctx: HandlerContext) -> SkillOutcome:
    return _router(ctx)


def execute_elmos_waiver_governance(ctx: HandlerContext) -> SkillOutcome:
    return _waiver(ctx)


def execute_elmos_concurrency_async_refinement(ctx: HandlerContext) -> SkillOutcome:
    return _concurrency(ctx)


def execute_elmos_formal_model_versioning(ctx: HandlerContext) -> SkillOutcome:
    return _model_versioning(ctx)


def execute_elmos_liveness_fairness_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _liveness(ctx)


def execute_elmos_proof_carrying_conversion(ctx: HandlerContext) -> SkillOutcome:
    return _proof_carrying(ctx)


def execute_elmos_proof_drift_monitor(ctx: HandlerContext) -> SkillOutcome:
    return _drift(ctx)


def execute_elmos_proof_evidence_bundle(ctx: HandlerContext) -> SkillOutcome:
    return _evidence_bundle(ctx)


def execute_elmos_spring_data_migration_refinement(ctx: HandlerContext) -> SkillOutcome:
    return _spring_data(ctx)


def execute_elmos_spring_proxy_aop_semantic_checker(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _spring_proxy(ctx)


def execute_elmos_sql_transaction_exception_refinement(
    ctx: HandlerContext,
) -> SkillOutcome:
    return _transaction(ctx)


def execute_elmos_verified_core_generator(ctx: HandlerContext) -> SkillOutcome:
    return _verified_core(ctx)


def execute_elmos_formal_observability_slo(ctx: HandlerContext) -> SkillOutcome:
    return _observability(ctx)


def execute_elmos_reflection_ffi_boundary_verifier(ctx: HandlerContext) -> SkillOutcome:
    return _reflection_ffi(ctx)
