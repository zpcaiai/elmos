"""Bounded semantic operations behind the exact 132-Skill allowlist."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterReceipt, ExecutionAdapter
from .canonical import (
    canonical_json,
    canonical_value,
    digest_value,
    validate_digest,
    validate_identifier,
)
from .contracts import (
    ArtifactRecord,
    EvidenceStatus,
    ExecutionStatus,
    Operation,
    SkillOutcome,
    SkillRequest,
    TrustedIdentity,
)
from .registry import SkillBinding
from .store import SemanticAssuranceStore


class HandlerError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HandlerContext:
    binding: SkillBinding
    request: SkillRequest
    identity: TrustedIdentity
    request_digest: str
    store: SemanticAssuranceStore
    adapter: ExecutionAdapter | None = None


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: str = "error",
    path: str = "$",
) -> dict[str, Any]:
    return {
        "code": validate_identifier(code, "diagnostic.code"),
        "severity": severity,
        "message": message,
        "path": path,
    }


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandlerError(f"{path}: expected object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise HandlerError(f"{path}: expected array")
    return value


def _required(payload: dict[str, Any], key: str) -> Any:
    if key not in payload:
        raise HandlerError(f"payload.{key}: required field is missing")
    return payload[key]


def _integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise HandlerError(f"{path}: expected integer")
    return value


def _artifact_contents(
    ctx: HandlerContext,
    *,
    execution_status: ExecutionStatus,
    evidence_status: EvidenceStatus,
    result: dict[str, Any],
    diagnostics: tuple[dict[str, Any], ...],
) -> tuple[tuple[ArtifactRecord, dict[str, Any]], ...]:
    scope_digest = digest_value(ctx.request.scope.to_dict())
    common = {
        "schemaVersion": "elmos.semantic-assurance.artifact/v1",
        "packageId": "elmos-semantic-assurance-expansion-skills-v1.0.0",
        "sourceSkillId": ctx.binding.source_skill_id,
        "skillName": ctx.binding.source_name,
        "installedName": ctx.binding.installed_name,
        "handlerId": ctx.binding.handler_id,
        "operation": ctx.binding.operation.value,
        "requestDigest": ctx.request_digest,
        "scopeDigest": scope_digest,
        "snapshotDigest": ctx.request.scope.snapshot_digest,
        "environmentDigest": ctx.request.scope.environment_digest,
        "toolchainDigest": ctx.request.scope.toolchain_digest,
        "semanticProfileDigest": ctx.request.scope.semantic_profile_digest,
        "producer": {
            "kind": "repository-owned-local-runtime",
            "actorId": ctx.identity.actor_id,
        },
    }
    documents: tuple[dict[str, Any], ...] = (
        {
            **common,
            "artifactRole": "model",
            "executionStatus": execution_status.value,
            "data": canonical_value(result),
        },
        {
            **common,
            "artifactRole": "evidence",
            "evidenceStatus": evidence_status.value,
            "externalEvidenceStatus": "NOT_RUN",
            "certificationStatus": "NOT_CERTIFIED",
            "evidenceTimeBasis": "response-metadata-only",
        },
        {
            **common,
            "artifactRole": "diagnostics",
            "diagnostics": [canonical_value(item) for item in diagnostics],
        },
    )
    artifacts: list[tuple[ArtifactRecord, dict[str, Any]]] = []
    for logical_path, document in zip(ctx.binding.outputs, documents, strict=True):
        encoded = canonical_json(document)
        artifacts.append(
            (
                ArtifactRecord(
                    logical_path=logical_path,
                    media_type="application/json",
                    content_digest=digest_value(document),
                    byte_count=len(encoded),
                ),
                document,
            )
        )
    return tuple(artifacts)


def _outcome(
    ctx: HandlerContext,
    result: dict[str, Any],
    *,
    execution_status: ExecutionStatus = ExecutionStatus.LOCAL_EXECUTED,
    evidence_status: EvidenceStatus = EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED,
    diagnostics: tuple[dict[str, Any], ...] = (),
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    artifact_contents = _artifact_contents(
        ctx,
        execution_status=execution_status,
        evidence_status=evidence_status,
        result=result,
        diagnostics=diagnostics,
    )
    outcome = SkillOutcome(
        skill_name=ctx.binding.source_name,
        source_skill_id=ctx.binding.source_skill_id,
        installed_name=ctx.binding.installed_name,
        handler_id=ctx.binding.handler_id,
        operation=ctx.binding.operation,
        capability_state=ctx.binding.capability_state,
        implementation_state=ctx.binding.capability_state.value,
        execution_status=execution_status,
        evidence_status=evidence_status,
        result=result,
        diagnostics=diagnostics,
        artifacts=tuple(item[0] for item in artifact_contents),
    )
    return outcome, artifact_contents


def _blocked(
    ctx: HandlerContext,
    code: str,
    message: str,
    result: dict[str, Any] | None = None,
    *,
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_RUN,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    return _outcome(
        ctx,
        result or {"readiness": "BLOCKED"},
        execution_status=ExecutionStatus.BLOCKED,
        evidence_status=evidence_status,
        diagnostics=(_diagnostic(code, message),),
    )


def _unknown_tuple_blocker(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]] | None:
    if not ctx.request.scope.contains_unknown_tuple:
        return None
    return _blocked(
        ctx,
        "UNKNOWN_RUNTIME_TUPLE",
        "source and target technology, dialect and runtime must be exact",
        {
            "readiness": "BLOCKED",
            "routeId": ctx.request.scope.route_id,
            "tuple": {
                "source": [
                    ctx.request.scope.source_technology,
                    ctx.request.scope.source_dialect,
                    ctx.request.scope.source_runtime,
                ],
                "target": [
                    ctx.request.scope.target_technology,
                    ctx.request.scope.target_dialect,
                    ctx.request.scope.target_runtime,
                ],
            },
        },
    )


def _model_normalization(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    blocked = _unknown_tuple_blocker(ctx)
    if blocked is not None:
        return blocked
    items = _list(_required(ctx.request.payload, "items"), "payload.items")
    if not items:
        return _blocked(
            ctx,
            "EMPTY_MODEL_INPUT",
            "at least one provenance-bound semantic item is required",
        )
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    blockers: list[str] = []
    allowed_states = {
        "KNOWN",
        "UNKNOWN",
        "UNSUPPORTED",
        "UNDEFINED",
        "IMPLEMENTATION_DEFINED",
        "NONDETERMINISTIC",
    }
    for index, raw in enumerate(items):
        item = _mapping(raw, f"payload.items[{index}]")
        item_id = validate_identifier(item.get("id"), f"payload.items[{index}].id")
        if item_id in seen:
            raise HandlerError(f"payload.items[{index}].id: duplicate identifier")
        seen.add(item_id)
        state = item.get("state", "KNOWN")
        if state not in allowed_states:
            raise HandlerError(f"payload.items[{index}].state: invalid semantic state")
        source_span = _mapping(item.get("sourceSpan"), f"payload.items[{index}].sourceSpan")
        artifact_digest = validate_digest(
            source_span.get("artifactDigest"),
            f"payload.items[{index}].sourceSpan.artifactDigest",
        )
        if artifact_digest not in {
            validate_digest(ctx.request.scope.source_digest),
            validate_digest(ctx.request.scope.target_digest),
        }:
            raise HandlerError(
                f"payload.items[{index}].sourceSpan: artifact digest is outside scope"
            )
        start = source_span.get("start")
        end = source_span.get("end")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end < start
        ):
            raise HandlerError(f"payload.items[{index}].sourceSpan: invalid byte range")
        if state != "KNOWN":
            blockers.append(item_id)
        normalized.append(
            {
                "id": item_id,
                "kind": validate_identifier(item.get("kind"), f"payload.items[{index}].kind"),
                "state": state,
                "sourceSpan": {
                    "artifactDigest": artifact_digest,
                    "start": start,
                    "end": end,
                },
                "semantics": canonical_value(item.get("semantics", {})),
                "provenance": canonical_value(item.get("provenance", {})),
            }
        )
    normalized.sort(key=lambda item: item["id"])
    result = {
        "modelVersion": "1.0.0",
        "itemCount": len(normalized),
        "items": normalized,
        "modelDigest": digest_value(normalized),
        "blockingItemIds": sorted(blockers),
        "readiness": "LOCAL_MODEL_READY" if not blockers else "BLOCKED",
    }
    if blockers:
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=EvidenceStatus.INCONCLUSIVE,
            diagnostics=(
                _diagnostic(
                    "EXPLICIT_SEMANTIC_UNCERTAINTY",
                    "critical unknown or unsupported semantic items remain",
                ),
            ),
        )
    return _outcome(ctx, result)


def _json_pointer(document: Any, pointer: str) -> Any:
    if pointer == "":
        return document
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise HandlerError("observablePaths entries must be RFC 6901 pointers")
    current = document
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise HandlerError(f"observable path does not exist: {pointer}")
    return current


def _semantic_comparison(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    blocked = _unknown_tuple_blocker(ctx)
    if blocked is not None:
        return blocked
    source = canonical_value(_required(ctx.request.payload, "source"))
    target = canonical_value(_required(ctx.request.payload, "target"))
    relation = ctx.request.payload.get("relation", "EXACT")
    if relation not in {"EXACT", "OBSERVATIONAL", "PERMITTED_REFINEMENT"}:
        raise HandlerError("payload.relation is invalid")
    compared_source = source
    compared_target = target
    compared_paths: list[str] = [""]
    if relation == "OBSERVATIONAL":
        paths = _list(
            _required(ctx.request.payload, "observablePaths"),
            "payload.observablePaths",
        )
        if not paths or any(not isinstance(item, str) for item in paths):
            raise HandlerError("payload.observablePaths must contain explicit paths")
        if len(paths) > 256:
            raise HandlerError("payload.observablePaths exceeds 256 entries")
        compared_paths = sorted(set(paths))
        compared_source = {
            path: canonical_value(_json_pointer(source, path)) for path in compared_paths
        }
        compared_target = {
            path: canonical_value(_json_pointer(target, path)) for path in compared_paths
        }
    elif relation == "PERMITTED_REFINEMENT":
        required_properties = _mapping(
            _required(ctx.request.payload, "requiredProperties"),
            "payload.requiredProperties",
        )
        compared_paths = sorted(required_properties)
        compared_source = {
            path: canonical_value(_json_pointer(source, path)) for path in compared_paths
        }
        compared_target = {
            path: canonical_value(_json_pointer(target, path)) for path in compared_paths
        }
        for path, expected in required_properties.items():
            if compared_target[path] != expected:
                compared_target[path] = {
                    "observed": compared_target[path],
                    "required": expected,
                }
    equal = compared_source == compared_target
    result: dict[str, Any] = {
        "relation": relation,
        "comparedPaths": compared_paths,
        "sourceObservationDigest": digest_value(compared_source),
        "targetObservationDigest": digest_value(compared_target),
        "verdict": "MATCH_WITHIN_DECLARED_SCOPE" if equal else "MISMATCH",
        "universalEquivalenceClaimed": False,
    }
    if not equal:
        counterexample = {
            "source": compared_source,
            "target": compared_target,
            "relation": relation,
        }
        result["counterexample"] = counterexample
        result["counterexampleDigest"] = digest_value(counterexample)
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.LOCAL_EXECUTED,
            evidence_status=EvidenceStatus.COUNTEREXAMPLE,
            diagnostics=(
                _diagnostic(
                    "SEMANTIC_MISMATCH",
                    "source and target differ under the declared comparison relation",
                ),
            ),
        )
    return _outcome(ctx, result)


def _analyze_graph(graph_value: Any, path: str) -> dict[str, Any]:
    graph = _mapping(graph_value, path)
    nodes = _list(graph.get("nodes"), f"{path}.nodes")
    edges = _list(graph.get("edges"), f"{path}.edges")
    node_ids: list[str] = []
    entry_ids: list[str] = []
    exit_ids: list[str] = []
    for index, raw in enumerate(nodes):
        node = _mapping(raw, f"{path}.nodes[{index}]")
        node_id = validate_identifier(node.get("id"), f"{path}.nodes[{index}].id")
        node_ids.append(node_id)
        if node.get("entry") is True:
            entry_ids.append(node_id)
        if node.get("exit") is True:
            exit_ids.append(node_id)
    if len(node_ids) != len(set(node_ids)):
        raise HandlerError(f"{path}.nodes contains duplicate IDs")
    node_set = set(node_ids)
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree = {node_id: 0 for node_id in node_ids}
    normalized_edges: list[dict[str, str]] = []
    dangling: list[dict[str, str]] = []
    for index, raw in enumerate(edges):
        edge = _mapping(raw, f"{path}.edges[{index}]")
        source = validate_identifier(edge.get("from"), f"{path}.edges[{index}].from")
        target = validate_identifier(edge.get("to"), f"{path}.edges[{index}].to")
        kind = validate_identifier(edge.get("kind", "flow"), f"{path}.edges[{index}].kind")
        normalized = {"from": source, "to": target, "kind": kind}
        normalized_edges.append(normalized)
        if source not in node_set or target not in node_set:
            dangling.append(normalized)
            continue
        adjacency[source].append(target)
        indegree[target] += 1
    queue = deque(sorted(node_id for node_id, count in indegree.items() if count == 0))
    topological: list[str] = []
    while queue:
        node_id = queue.popleft()
        topological.append(node_id)
        for target in sorted(adjacency[node_id]):
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    cyclic = len(topological) != len(node_ids)
    normalized_edges.sort(key=lambda item: (item["from"], item["to"], item["kind"]))
    return {
        "nodeCount": len(node_ids),
        "edgeCount": len(normalized_edges),
        "entryIds": sorted(entry_ids),
        "exitIds": sorted(exit_ids),
        "danglingEdges": dangling,
        "cyclic": cyclic,
        "topologicalOrder": [] if cyclic else topological,
        "graphDigest": digest_value({"nodes": sorted(node_ids), "edges": normalized_edges}),
    }


def _graph_analysis(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    blocked = _unknown_tuple_blocker(ctx)
    if blocked is not None:
        return blocked
    payload = ctx.request.payload
    if "sourceGraph" in payload or "targetGraph" in payload:
        if "sourceGraph" not in payload or "targetGraph" not in payload:
            raise HandlerError("both sourceGraph and targetGraph are required")
        source = _analyze_graph(payload["sourceGraph"], "payload.sourceGraph")
        target = _analyze_graph(payload["targetGraph"], "payload.targetGraph")
        comparable = {
            key: source[key] for key in ("nodeCount", "edgeCount", "entryIds", "exitIds", "cyclic")
        } == {
            key: target[key] for key in ("nodeCount", "edgeCount", "entryIds", "exitIds", "cyclic")
        }
        result = {
            "sourceGraph": source,
            "targetGraph": target,
            "verdict": "STRUCTURALLY_MATCHED" if comparable else "MISMATCH",
            "graphIsomorphismClaimed": False,
        }
    else:
        analysis = _analyze_graph(_required(payload, "graph"), "payload.graph")
        acyclic_required = payload.get("acyclicRequired", False)
        entry_required = payload.get("singleEntryRequired", False)
        exit_required = payload.get("exitRequired", False)
        valid = (
            not analysis["danglingEdges"]
            and (not acyclic_required or not analysis["cyclic"])
            and (not entry_required or len(analysis["entryIds"]) == 1)
            and (not exit_required or len(analysis["exitIds"]) >= 1)
        )
        result = {**analysis, "verdict": "VALID_WITHIN_DECLARED_RULES" if valid else "MALFORMED"}
        comparable = valid
    if not comparable:
        return _outcome(
            ctx,
            result,
            evidence_status=EvidenceStatus.COUNTEREXAMPLE,
            diagnostics=(
                _diagnostic("GRAPH_SEMANTIC_MISMATCH", "graph obligations are not satisfied"),
            ),
        )
    return _outcome(ctx, result)


def _coverage_analysis(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    dimensions = _list(_required(ctx.request.payload, "dimensions"), "payload.dimensions")
    if not dimensions:
        return _blocked(ctx, "EMPTY_COVERAGE_DENOMINATOR", "coverage requires explicit dimensions")
    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, raw in enumerate(dimensions):
        item = _mapping(raw, f"payload.dimensions[{index}]")
        identifier = validate_identifier(item.get("id"), f"payload.dimensions[{index}].id")
        numerator = _integer(item.get("numerator"), f"payload.dimensions[{index}].numerator")
        denominator = _integer(item.get("denominator"), f"payload.dimensions[{index}].denominator")
        threshold_numerator = _integer(
            item.get("thresholdNumerator", denominator),
            f"payload.dimensions[{index}].thresholdNumerator",
        )
        threshold_denominator = _integer(
            item.get("thresholdDenominator", denominator),
            f"payload.dimensions[{index}].thresholdDenominator",
        )
        if denominator <= 0 or threshold_denominator <= 0:
            blockers.append(identifier)
            passed = False
        elif numerator < 0 or numerator > denominator:
            raise HandlerError(f"payload.dimensions[{index}]: numerator is outside denominator")
        elif threshold_numerator < 0 or threshold_numerator > threshold_denominator:
            raise HandlerError(f"payload.dimensions[{index}]: invalid threshold fraction")
        else:
            passed = numerator * threshold_denominator >= threshold_numerator * denominator
            if not passed:
                blockers.append(identifier)
        normalized.append(
            {
                "id": identifier,
                "numerator": numerator,
                "denominator": denominator,
                "ratio": None if denominator <= 0 else f"{numerator}/{denominator}",
                "threshold": f"{threshold_numerator}/{threshold_denominator}",
                "passed": passed,
            }
        )
    result = {
        "dimensions": normalized,
        "blockingDimensions": blockers,
        "verdict": "LOCAL_THRESHOLD_MET" if not blockers else "BLOCKED",
        "certifiable": False,
    }
    if blockers:
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=EvidenceStatus.INCONCLUSIVE,
            diagnostics=(
                _diagnostic(
                    "COVERAGE_THRESHOLD_NOT_MET",
                    "one or more explicit denominators are missing or below threshold",
                ),
            ),
        )
    return _outcome(ctx, result)


def _corpus_governance(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    fixtures = _list(_required(ctx.request.payload, "fixtures"), "payload.fixtures")
    if not fixtures:
        return _blocked(
            ctx,
            "EMPTY_CORPUS",
            "a certification corpus cannot be inferred from an empty fixture list",
        )
    allowed_partitions = {"development", "negative", "holdout", "representative"}
    ids: set[str] = set()
    digest_partitions: dict[str, set[str]] = defaultdict(set)
    normalized: list[dict[str, Any]] = []
    blockers: list[str] = []
    for index, raw in enumerate(fixtures):
        fixture = _mapping(raw, f"payload.fixtures[{index}]")
        fixture_id = validate_identifier(fixture.get("id"), f"payload.fixtures[{index}].id")
        if fixture_id in ids:
            raise HandlerError("fixture IDs must be unique")
        ids.add(fixture_id)
        content_digest = validate_digest(
            fixture.get("contentDigest"), f"payload.fixtures[{index}].contentDigest"
        )
        partition = fixture.get("partition")
        if partition not in allowed_partitions:
            raise HandlerError(f"payload.fixtures[{index}].partition is invalid")
        digest_partitions[content_digest].add(partition)
        license_value = _mapping(fixture.get("license"), f"payload.fixtures[{index}].license")
        spdx = license_value.get("spdx")
        review = license_value.get("reviewStatus")
        provenance_digest = license_value.get("provenanceDigest")
        if not isinstance(spdx, str) or not spdx or spdx.upper() in {"UNKNOWN", "PENDING"}:
            blockers.append(fixture_id)
        if review != "APPROVED":
            blockers.append(fixture_id)
        validate_digest(provenance_digest, f"payload.fixtures[{index}].license.provenanceDigest")
        normalized.append(
            {
                "id": fixture_id,
                "contentDigest": content_digest,
                "partition": partition,
                "license": {
                    "spdx": spdx,
                    "reviewStatus": review,
                    "provenanceDigest": validate_digest(provenance_digest),
                },
            }
        )
    leaked = sorted(
        digest for digest, partitions in digest_partitions.items() if len(partitions) > 1
    )
    result = {
        "fixtureCount": len(normalized),
        "partitionCounts": dict(sorted(Counter(item["partition"] for item in normalized).items())),
        "fixtures": sorted(normalized, key=lambda item: item["id"]),
        "crossPartitionDuplicateDigests": leaked,
        "provenanceBlockers": sorted(set(blockers)),
        "verdict": "LOCAL_CORPUS_REGISTERED" if not blockers and not leaked else "BLOCKED",
        "externalCorpusEvidence": "NOT_RUN",
    }
    if blockers or leaked:
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=EvidenceStatus.INCONCLUSIVE,
            diagnostics=(
                _diagnostic(
                    "CORPUS_GOVERNANCE_BLOCKED",
                    "license, provenance or partition independence requirements failed",
                ),
            ),
        )
    return _outcome(ctx, result)


def _validate_evidence_item(
    ctx: HandlerContext, item: dict[str, Any], path: str
) -> tuple[dict[str, Any], list[str]]:
    state = item.get("state")
    allowed_states = {status.value for status in EvidenceStatus}
    if state not in allowed_states:
        raise HandlerError(f"{path}.state is invalid")
    blockers: list[str] = []
    expected_digests = {
        "subjectDigest": ctx.request.scope.source_digest,
        "snapshotDigest": ctx.request.scope.snapshot_digest,
        "environmentDigest": ctx.request.scope.environment_digest,
        "toolchainDigest": ctx.request.scope.toolchain_digest,
        "corpusDigest": ctx.request.scope.corpus_digest,
        "assumptionsDigest": ctx.request.scope.assumptions_digest,
    }
    normalized: dict[str, Any] = {"state": state}
    for field_name, expected in expected_digests.items():
        observed = validate_digest(item.get(field_name), f"{path}.{field_name}")
        normalized[field_name] = observed
        if observed != validate_digest(expected):
            blockers.append(f"{field_name}:stale-or-wrong-scope")
    executor = item.get("executorId")
    verifier = item.get("verifierId")
    if executor is not None:
        normalized["executorId"] = validate_identifier(executor, f"{path}.executorId")
    if verifier is not None:
        normalized["verifierId"] = validate_identifier(verifier, f"{path}.verifierId")
    normalized["signed"] = item.get("signed") is True
    if state == EvidenceStatus.INDEPENDENTLY_VERIFIED.value:
        if not executor or not verifier or executor == verifier:
            blockers.append("independent-verifier-missing")
        if item.get("signed") is not True:
            blockers.append("signature-missing")
        validate_digest(item.get("trustStoreDigest"), f"{path}.trustStoreDigest")
        if item.get("revocationChecked") is not True:
            blockers.append("revocation-not-checked")
        normalized["trustStoreDigest"] = validate_digest(item["trustStoreDigest"])
        normalized["revocationChecked"] = True
        blockers.append("external-signature-not-cryptographically-verified")
    return normalized, blockers


def _evidence_validation(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    evidence = _list(_required(ctx.request.payload, "evidence"), "payload.evidence")
    if not evidence:
        return _blocked(ctx, "EVIDENCE_NOT_RUN", "no evidence receipts were supplied")
    normalized: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    counterexample_indexes: list[int] = []
    for index, raw in enumerate(evidence):
        item = _mapping(raw, f"payload.evidence[{index}]")
        normalized_item, item_blockers = _validate_evidence_item(
            ctx, item, f"payload.evidence[{index}]"
        )
        normalized.append(normalized_item)
        blockers.extend({"index": index, "reason": reason} for reason in item_blockers)
        if item.get("state") in {
            EvidenceStatus.NOT_RUN.value,
            EvidenceStatus.INCONCLUSIVE.value,
            EvidenceStatus.EXTERNAL_EVIDENCE_PENDING.value,
        }:
            blockers.append({"index": index, "reason": "non-success-evidence-state"})
        if item.get("state") == EvidenceStatus.COUNTEREXAMPLE.value:
            counterexample_indexes.append(index)
    result = {
        "evidenceCount": len(normalized),
        "evidence": normalized,
        "blockers": blockers,
        "verdict": (
            "BLOCKED"
            if blockers
            else "COUNTEREXAMPLE_BOUND"
            if counterexample_indexes
            else "EVIDENCE_BOUND_LOCAL"
        ),
        "counterexampleIndexes": counterexample_indexes,
        "independentCertificationClaimed": False,
    }
    if blockers:
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=EvidenceStatus.INCONCLUSIVE,
            diagnostics=(
                _diagnostic(
                    "EVIDENCE_VALIDATION_FAILED",
                    "evidence is missing, stale, self-conflicting or non-success",
                ),
            ),
        )
    if counterexample_indexes:
        return _outcome(
            ctx,
            result,
            evidence_status=EvidenceStatus.COUNTEREXAMPLE,
        )
    return _outcome(ctx, result)


_FORBIDDEN_PLAN_FIELDS = {
    "argv",
    "binary",
    "command",
    "cwd",
    "endpoint",
    "executable",
    "host",
    "shell",
    "script",
    "uri",
    "url",
    "workingdirectory",
    "environment",
    "env",
    "token",
    "secret",
}


def _forbidden_authority_paths(value: Any, path: str = "payload.plan") -> list[str]:
    """Find nested process, network, environment or secret authority fields."""

    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = "".join(character for character in key.lower() if character.isalnum())
            if normalized in _FORBIDDEN_PLAN_FIELDS:
                found.append(f"{path}.{key}")
            found.extend(_forbidden_authority_paths(item, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_authority_paths(item, f"{path}[{index}]"))
    return found


def _adapter_execution(
    ctx: HandlerContext,
    *,
    kind: str,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    blocked = _unknown_tuple_blocker(ctx)
    if blocked is not None:
        return blocked
    plan_input = _mapping(_required(ctx.request.payload, "plan"), "payload.plan")
    forbidden = sorted(_forbidden_authority_paths(plan_input))
    if forbidden:
        raise HandlerError(f"payload.plan contains forbidden authority fields: {forbidden}")
    adapter_id = validate_identifier(plan_input.get("adapterId"), "payload.plan.adapterId")
    action = validate_identifier(plan_input.get("action"), "payload.plan.action")
    arguments = _mapping(plan_input.get("arguments", {}), "payload.plan.arguments")
    plan = {
        "schemaVersion": "elmos.semantic-assurance.execution-plan/v1",
        "kind": kind,
        "skillName": ctx.binding.source_name,
        "adapterId": adapter_id,
        "action": action,
        "arguments": canonical_value(arguments),
        "scopeDigest": digest_value(ctx.request.scope.to_dict()),
        "requestDigest": ctx.request_digest,
        "networkDefault": "DENY",
        "sourceMount": "READ_ONLY",
        "secrets": "REFERENCE_ONLY",
    }
    plan_digest = digest_value(plan)
    if ctx.adapter is None:
        return _outcome(
            ctx,
            {
                "plan": plan,
                "planDigest": plan_digest,
                "verdict": "REQUIRES_ADAPTER",
            },
            execution_status=ExecutionStatus.REQUIRES_ADAPTER,
            evidence_status=EvidenceStatus.NOT_RUN,
            diagnostics=(
                _diagnostic("ADAPTER_NOT_CONFIGURED", f"trusted {kind} adapter is required"),
            ),
        )
    if getattr(ctx.adapter, "adapter_id", None) != adapter_id:
        raise HandlerError("configured adapter identity does not match the bound plan")
    supported_actions = getattr(ctx.adapter, "supported_actions", None)
    if not isinstance(supported_actions, frozenset) or action not in supported_actions:
        raise HandlerError("configured adapter does not allow the requested typed action")
    receipt = ctx.adapter.execute(plan, ctx.request.scope)
    _validate_adapter_receipt(ctx, receipt, plan_digest)
    receipt_value = receipt.to_dict()
    result = {
        "plan": plan,
        "planDigest": plan_digest,
        "receipt": receipt_value,
        "receiptDigest": digest_value(receipt_value),
        "verdict": receipt.status,
        "independentEvidenceClaimed": False,
    }
    if receipt.status == "COUNTEREXAMPLE":
        return _outcome(
            ctx,
            result,
            evidence_status=EvidenceStatus.COUNTEREXAMPLE,
            diagnostics=(
                _diagnostic(
                    "ADAPTER_COUNTEREXAMPLE",
                    "adapter returned a replayable counterexample",
                ),
            ),
        )
    if receipt.status != "PASS":
        evidence_state = (
            EvidenceStatus.INCONCLUSIVE
            if receipt.status in {"UNKNOWN", "TIMEOUT", "UNSUPPORTED"}
            else EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED
        )
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=evidence_state,
            diagnostics=(
                _diagnostic(
                    "ADAPTER_NON_SUCCESS",
                    "adapter result cannot satisfy the semantic obligation",
                ),
            ),
        )
    return _outcome(ctx, result)


def _validate_adapter_receipt(
    ctx: HandlerContext, receipt: AdapterReceipt, plan_digest: str
) -> None:
    if receipt.adapter_id != getattr(ctx.adapter, "adapter_id", None):
        raise HandlerError("adapter receipt identity mismatch")
    if validate_digest(receipt.request_digest) != validate_digest(plan_digest):
        raise HandlerError("adapter receipt request digest mismatch")
    if validate_digest(receipt.scope_digest) != digest_value(ctx.request.scope.to_dict()):
        raise HandlerError("adapter receipt scope digest mismatch")
    if validate_digest(receipt.evidence_digest) != digest_value(receipt.output):
        raise HandlerError("adapter receipt evidence digest mismatch")


def _native_execution(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    return _adapter_execution(ctx, kind="native-runtime")


def _formal_execution(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    return _adapter_execution(ctx, kind="formal-proof")


def _fuzz_execution(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    plan = ctx.request.payload.get("plan")
    if isinstance(plan, dict):
        arguments = plan.get("arguments")
        iterations = arguments.get("iterations") if isinstance(arguments, dict) else None
        if iterations is not None and (
            not isinstance(iterations, int)
            or isinstance(iterations, bool)
            or not 1 <= iterations <= 1_000_000
        ):
            raise HandlerError("fuzz iterations must be between 1 and 1,000,000")
    return _adapter_execution(ctx, kind="semantic-fuzz")


def _gate_evaluation(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    dependency_evidence = _mapping(
        _required(ctx.request.payload, "dependencyEvidence"),
        "payload.dependencyEvidence",
    )
    blockers: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    for dependency in ctx.binding.dependencies:
        raw = dependency_evidence.get(dependency)
        if not isinstance(raw, dict):
            blockers.append({"dependency": dependency, "reason": "MISSING"})
            continue
        normalized, item_blockers = _validate_evidence_item(
            ctx, raw, f"payload.dependencyEvidence.{dependency}"
        )
        state = raw.get("state")
        if state not in {
            EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED.value,
            EvidenceStatus.INDEPENDENTLY_VERIFIED.value,
        }:
            item_blockers.append("NON_SUCCESS_STATE")
        if item_blockers:
            blockers.extend(
                {"dependency": dependency, "reason": reason} for reason in item_blockers
            )
        else:
            accepted.append({"dependency": dependency, **normalized})
    unexpected = sorted(set(dependency_evidence) - set(ctx.binding.dependencies))
    if unexpected:
        blockers.append({"dependency": "*", "reason": f"UNEXPECTED:{','.join(unexpected)}"})
    route_profile = ctx.request.payload.get("routeProfile")
    if not isinstance(route_profile, dict):
        blockers.append({"dependency": "route-profile", "reason": "MISSING_PACKAGE_PROFILE"})
    else:
        observed = validate_digest(
            route_profile.get("profileDigest"),
            "payload.routeProfile.profileDigest",
        )
        if observed != validate_digest(ctx.request.scope.semantic_profile_digest):
            blockers.append({"dependency": "route-profile", "reason": "PROFILE_DIGEST_MISMATCH"})
        if route_profile.get("source") not in {"trusted-host", "independent-verifier"}:
            blockers.append({"dependency": "route-profile", "reason": "UNTRUSTED_PROFILE_SOURCE"})
    result = {
        "evaluatedDependencies": len(ctx.binding.dependencies),
        "acceptedEvidence": accepted,
        "blockers": blockers,
        "readiness": "BLOCKED" if blockers else "READY_FOR_EXTERNAL_GATE",
        "certification": "NOT_CERTIFIED",
        "externalEvidenceStatus": "NOT_RUN",
    }
    if blockers:
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=EvidenceStatus.INCONCLUSIVE,
            diagnostics=(
                _diagnostic(
                    "CONSERVATIVE_GATE_BLOCKED",
                    "missing, stale, unknown or untrusted evidence cannot pass",
                ),
            ),
        )
    return _outcome(ctx, result)


_CACHE_IDENTITY_FIELDS = (
    "formulaDigest",
    "semanticModelDigest",
    "assumptionsDigest",
    "toolchainDigest",
    "sourceDigest",
    "targetDigest",
    "environmentDigest",
    "corpusDigest",
)


def _cache_invalidation(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    identity = _mapping(_required(ctx.request.payload, "cacheIdentity"), "payload.cacheIdentity")
    missing = [field for field in _CACHE_IDENTITY_FIELDS if field not in identity]
    if missing:
        raise HandlerError(f"payload.cacheIdentity missing fields: {missing}")
    normalized = {
        field: validate_digest(identity[field], f"payload.cacheIdentity.{field}")
        for field in _CACHE_IDENTITY_FIELDS
    }
    expected = {
        "assumptionsDigest": ctx.request.scope.assumptions_digest,
        "toolchainDigest": ctx.request.scope.toolchain_digest,
        "sourceDigest": ctx.request.scope.source_digest,
        "targetDigest": ctx.request.scope.target_digest,
        "environmentDigest": ctx.request.scope.environment_digest,
        "corpusDigest": ctx.request.scope.corpus_digest,
    }
    mismatched = [
        field for field, value in expected.items() if normalized[field] != validate_digest(value)
    ]
    if mismatched:
        return _blocked(
            ctx,
            "CACHE_SCOPE_MISMATCH",
            "cache identity does not match the trusted semantic scope",
            {"mismatchedFields": mismatched, "readiness": "BLOCKED"},
        )
    cache_key = digest_value(normalized)
    dependency_digest = digest_value(
        {field: normalized[field] for field in _CACHE_IDENTITY_FIELDS[1:]}
    )
    invalidated = ctx.store.invalidate_cache(
        ctx.request.scope,
        ctx.binding.source_name,
        dependency_digest,
    )
    registration = None
    if "result" in ctx.request.payload:
        result_value = _mapping(ctx.request.payload["result"], "payload.result")
        registration = ctx.store.put_cache(
            ctx.request.scope,
            ctx.binding.source_name,
            cache_key,
            dependency_digest,
            result_value,
        )
    return _outcome(
        ctx,
        {
            "cacheKey": cache_key,
            "dependencyDigest": dependency_digest,
            "invalidatedEntries": invalidated,
            "registration": registration,
            "fullSemanticIdentityBound": True,
        },
    )


def _counterexample_replay(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    counterexample = _mapping(
        _required(ctx.request.payload, "counterexample"), "payload.counterexample"
    )
    replay = _mapping(_required(ctx.request.payload, "replay"), "payload.replay")
    counterexample_id = validate_identifier(counterexample.get("id"), "payload.counterexample.id")
    expected_source = validate_digest(
        counterexample.get("sourceTraceDigest"),
        "payload.counterexample.sourceTraceDigest",
    )
    expected_target = validate_digest(
        counterexample.get("targetTraceDigest"),
        "payload.counterexample.targetTraceDigest",
    )
    observed_source = digest_value(replay.get("sourceTrace"))
    observed_target = digest_value(replay.get("targetTrace"))
    reproduced = observed_source == expected_source and observed_target == expected_target
    result = {
        "counterexampleId": counterexample_id,
        "expectedSourceTraceDigest": expected_source,
        "observedSourceTraceDigest": observed_source,
        "expectedTargetTraceDigest": expected_target,
        "observedTargetTraceDigest": observed_target,
        "reproduced": reproduced,
        "replayDigest": digest_value(replay),
    }
    if not reproduced:
        return _outcome(
            ctx,
            result,
            execution_status=ExecutionStatus.BLOCKED,
            evidence_status=EvidenceStatus.INCONCLUSIVE,
            diagnostics=(
                _diagnostic(
                    "COUNTEREXAMPLE_NOT_REPRODUCED",
                    "replay traces do not match the bound counterexample",
                ),
            ),
        )
    return _outcome(
        ctx,
        result,
        evidence_status=EvidenceStatus.COUNTEREXAMPLE,
    )


OperationHandler = Callable[
    [HandlerContext],
    tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]],
]


OPERATION_HANDLERS: dict[Operation, OperationHandler] = {
    Operation.MODEL_NORMALIZATION: _model_normalization,
    Operation.SEMANTIC_COMPARISON: _semantic_comparison,
    Operation.GRAPH_ANALYSIS: _graph_analysis,
    Operation.COVERAGE_ANALYSIS: _coverage_analysis,
    Operation.CORPUS_GOVERNANCE: _corpus_governance,
    Operation.EVIDENCE_VALIDATION: _evidence_validation,
    Operation.NATIVE_EXECUTION: _native_execution,
    Operation.FORMAL_EXECUTION: _formal_execution,
    Operation.FUZZ_EXECUTION: _fuzz_execution,
    Operation.GATE_EVALUATION: _gate_evaluation,
    Operation.CACHE_INVALIDATION: _cache_invalidation,
    Operation.COUNTEREXAMPLE_REPLAY: _counterexample_replay,
}


def execute_binding(
    ctx: HandlerContext,
) -> tuple[SkillOutcome, tuple[tuple[ArtifactRecord, dict[str, Any]], ...]]:
    try:
        handler = OPERATION_HANDLERS[ctx.binding.operation]
    except KeyError as exc:  # pragma: no cover - registry validation is authoritative
        raise HandlerError(f"no operation handler for {ctx.binding.operation.value}") from exc
    return handler(ctx)


__all__ = [
    "OPERATION_HANDLERS",
    "HandlerContext",
    "HandlerError",
    "execute_binding",
]
