"""Six exact, bounded local Dataset Foundry algorithms.

Inputs are caller-provided facts, never verified provenance or training consent.
The local algorithms produce quarantine-bound data products only. They do not
run training, delete data, execute source code, verify identities, or establish
independent evidence. Python AST equality is structural, not behavioral proof.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Mapping
from datetime import datetime, timezone
from fractions import Fraction
import sys
from typing import Any

from .canonical import canonical_digest, canonical_value, require_identifier, validate_digest
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    _exact_mapping,
    _mapping,
    _number,
    _response,
    _sequence,
    _text,
    _topological_order,
)
from .store import FoundryStore


DATASET_SEMANTIC_SKILLS: frozenset[str] = frozenset(
    {
        "repo-org-time-split-builder",
        "dataset-lineage-and-provenance",
        "dataset-revocation-unlearning-index",
        "preference-pair-builder",
        "active-learning-sample-selection",
        "semantic-and-ast-deduplication",
    }
)

_INPUT_KEYS = {"experience episode", "knowledge object", "human feedback", "verification evidence"}
_METRICS = {"uncertainty", "business_value", "failure_frequency", "information_gain"}
_MAX_RECORDS = 2_000


def _values(payload: Mapping[str, Any], *, preference: bool = False) -> Mapping[str, Any]:
    values = _exact_mapping(payload.get("inputs"), "inputs", _INPUT_KEYS)
    canonical_value(values)  # Enforce total payload, depth, string and numeric bounds.
    for key in _INPUT_KEYS:
        if not _mapping(values[key], key):
            raise ValueError(f"{key} must be a non-empty object")
    if not preference:
        for key in ("human feedback", "verification evidence"):
            unused = _exact_mapping(values[key], key, {"status"})
            if unused["status"] != "NOT_RUN":
                raise ValueError(f"{key} cannot claim verification for this local algorithm")
    return values


def _experience_binding(values: Mapping[str, Any]) -> None:
    context = _exact_mapping(values["knowledge object"], "knowledge object", {"experience_digest"})
    if validate_digest(context["experience_digest"], "experience_digest") != canonical_digest(
        values["experience episode"]
    ):
        raise ValueError("knowledge context does not bind the exact experience input")


def _integer(value: Any, label: str, *, minimum: int = 0, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return int(value)


def _unique_records(
    value: Any, label: str, keys: set[str], id_key: str
) -> dict[str, Mapping[str, Any]]:
    records: dict[str, Mapping[str, Any]] = {}
    for raw in _sequence(value, label, maximum=_MAX_RECORDS):
        item = _exact_mapping(raw, label, keys)
        identity = require_identifier(item[id_key], f"{label}.{id_key}")
        if identity in records:
            raise ValueError(f"{label} contains duplicate identities")
        records[identity] = item
    return dict(sorted(records.items()))


def _scope_record(record: Mapping[str, Any], scope: TenantScope) -> None:
    if record["tenant_id"] != scope.tenant_id or record["project_id"] != scope.project_id:
        raise ValueError("dataset record crosses the authenticated tenant/project boundary")


def _result(
    skill_name: str,
    values: Mapping[str, Any],
    scope: TenantScope,
    items: list[Mapping[str, Any]],
    analysis: Mapping[str, Any],
    lineage: Mapping[str, Any],
    limitations: list[str],
) -> Mapping[str, Any]:
    body = {
        "schema_version": "elmos.foundry.dataset-local.v1",
        "skill_name": skill_name,
        "tenant_id": scope.tenant_id,
        "project_id": scope.project_id,
        "input_digest": canonical_digest(values),
        "items": items,
        "analysis": analysis,
        "quarantine": True,
    }
    digest = canonical_digest(body)
    return _response(
        {
            "versioned dataset": {
                **body,
                "dataset_id": "dataset-" + digest[7:39],
                "content_digest": digest,
            },
            "dataset card": {
                "item_count": len(items),
                "implementation_scope": "BOUNDED_LOCAL_ALGORITHM",
                "limitations": limitations,
                "caller_facts_verified": False,
                "raw_customer_content_stored": False,
                "independent_corpus_status": "NOT_ESTABLISHED",
            },
            "lineage graph": {
                **lineage,
                "input_digest": canonical_digest(values),
                "provenance_verification": "NOT_RUN",
            },
            "training eligibility decision": {
                "decision": "EVIDENCE_PENDING",
                "eligible": False,
                "training_authorized": False,
                "reason_codes": ["trusted-consent-required", "independent-evidence-required"],
                "external_evidence_status": "NOT_RUN",
                "certification_status": "NOT_CERTIFIED",
            },
        }
    )


def _timestamp(value: Any, label: str) -> datetime:
    text = _text(value, label, maximum=64)
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if result.tzinfo is None or "T" not in text:
        raise ValueError(f"{label} must include time and timezone")
    return result.astimezone(timezone.utc)


def _split(
    skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
) -> Mapping[str, Any]:
    values = _values(payload)
    episodes = _exact_mapping(values["experience episode"], "experience episode", {"samples"})
    config = _exact_mapping(
        values["knowledge object"], "knowledge object", {"train_before", "validation_before"}
    )
    train_before = _timestamp(config["train_before"], "train_before")
    validation_before = _timestamp(config["validation_before"], "validation_before")
    if train_before >= validation_before:
        raise ValueError("split cutoffs must be strictly increasing")
    records = _unique_records(
        episodes["samples"],
        "samples",
        {
            "sample_id",
            "tenant_id",
            "project_id",
            "repository_id",
            "organization_id",
            "fork_family_id",
            "task_family_id",
            "observed_at",
            "content_digest",
        },
        "sample_id",
    )
    parent = {identity: identity for identity in records}

    def root(identity: str) -> str:
        while identity != parent[identity]:
            parent[identity] = parent[parent[identity]]
            identity = parent[identity]
        return identity

    first_seen: dict[tuple[str, str], str] = {}
    timestamps: dict[str, datetime] = {}
    for identity, item in records.items():
        _scope_record(item, scope)
        timestamps[identity] = _timestamp(item["observed_at"], "observed_at")
        validate_digest(item["content_digest"])
        for field in (
            "repository_id",
            "organization_id",
            "fork_family_id",
            "task_family_id",
            "content_digest",
        ):
            group = require_identifier(item[field], field)
            key = (field, group)
            if key in first_seen:
                left, right = sorted((root(identity), root(first_seen[key])))
                parent[right] = left
            else:
                first_seen[key] = identity
    groups: dict[str, list[str]] = defaultdict(list)
    for identity in records:
        groups[root(identity)].append(identity)
    items: list[Mapping[str, Any]] = []
    components: list[Mapping[str, Any]] = []
    for members in sorted(groups.values()):
        temporal_splits = {
            "train"
            if timestamps[member] < train_before
            else "validation"
            if timestamps[member] < validation_before
            else "holdout"
            for member in members
        }
        # A group spanning a cutoff cannot satisfy both strict time and group
        # isolation. Quarantine it explicitly rather than move future data back.
        split = next(iter(temporal_splits)) if len(temporal_splits) == 1 else "quarantine"
        group_id = canonical_digest(members)
        components.append({"group_id": group_id, "sample_ids": members, "split": split})
        for member in members:
            items.append(
                {
                    "sample_id": member,
                    "group_id": group_id,
                    "split": split,
                    "content_digest": records[member]["content_digest"],
                }
            )
    return _result(
        skill_name,
        values,
        scope,
        sorted(items, key=lambda item: str(item["sample_id"])),
        {
            "algorithm": "transitive-identity-components-strict-time-v1",
            "components": components,
            "quarantined_sample_count": sum(item["split"] == "quarantine" for item in items),
            "cutoff_semantics": "train < train_before; validation < validation_before; else holdout",
        },
        {"components": components},
        [
            "Identity completeness and accuracy require a trusted repository inventory.",
            "Components spanning time cutoffs are excluded from all three splits.",
            "No random balancing, unknown family inference, or external holdout qualification.",
        ],
    )


_NODE_KINDS = {
    "object",
    "task",
    "model",
    "skill",
    "human-edit",
    "transform",
    "sample",
    "dataset",
    "checkpoint",
    "adapter",
}
_RELATIONS: Mapping[str, tuple[set[str], set[str]]] = {
    "contributed-to": ({"object", "task", "model", "skill", "human-edit"}, {"transform", "sample"}),
    "derived-from": ({"object", "sample", "transform"}, {"sample", "transform"}),
    "member-of": ({"sample"}, {"dataset"}),
    "trained-into": ({"dataset", "checkpoint"}, {"checkpoint"}),
    "adapted-into": ({"dataset", "checkpoint", "adapter"}, {"adapter"}),
}


def _graph(
    values: Mapping[str, Any], scope: TenantScope
) -> tuple[
    dict[str, Mapping[str, Any]], list[Mapping[str, Any]], tuple[str, ...], dict[str, list[str]]
]:
    graph = _exact_mapping(values["experience episode"], "experience episode", {"nodes", "edges"})
    nodes = _unique_records(
        graph["nodes"],
        "nodes",
        {
            "node_id",
            "kind",
            "content_digest",
            "version",
            "tenant_id",
            "project_id",
        },
        "node_id",
    )
    for node in nodes.values():
        _scope_record(node, scope)
        if require_identifier(node["kind"], "kind") not in _NODE_KINDS:
            raise ValueError("unsupported lineage node kind")
        require_identifier(node["version"], "version")
        validate_digest(node["content_digest"])
    dependencies: dict[str, list[str]] = {node: [] for node in nodes}
    outgoing: dict[str, list[str]] = {node: [] for node in nodes}
    edges: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in _sequence(graph["edges"], "edges", minimum=0, maximum=10_000):
        edge = _exact_mapping(raw, "edge", {"parent", "child", "relation"})
        source = require_identifier(edge["parent"], "parent")
        target = require_identifier(edge["child"], "child")
        relation = require_identifier(edge["relation"], "relation")
        if source not in nodes or target not in nodes:
            raise ValueError("lineage has a dangling edge")
        if (source, target) in seen:
            raise ValueError("lineage has a duplicate edge")
        seen.add((source, target))
        if relation not in _RELATIONS:
            raise ValueError("unsupported lineage relation")
        source_kinds, target_kinds = _RELATIONS[relation]
        if nodes[source]["kind"] not in source_kinds or nodes[target]["kind"] not in target_kinds:
            raise ValueError("lineage edge violates its typed relation")
        dependencies[target].append(source)
        outgoing[source].append(target)
        edges.append(dict(edge))
    order = _topological_order(dependencies)
    for node_id, node in nodes.items():
        if (
            node["kind"] in {"sample", "dataset", "transform", "checkpoint", "adapter"}
            and not dependencies[node_id]
        ):
            raise ValueError("derived lineage node has no declared provenance")
    return nodes, sorted(edges, key=lambda edge: (edge["parent"], edge["child"])), order, outgoing


def _lineage(
    skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
) -> Mapping[str, Any]:
    values = _values(payload)
    nodes, edges, order, _ = _graph(values, scope)
    _experience_binding(values)
    ancestors: dict[str, set[str]] = {identity: set() for identity in nodes}
    parents: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        parents[edge["child"]].append(edge["parent"])
    for identity in order:
        for parent in parents[identity]:
            ancestors[identity].add(parent)
            ancestors[identity].update(ancestors[parent])
    items: list[Mapping[str, Any]] = [
        {
            "sample_id": identity,
            "source_node_ids": sorted(ancestors[identity]),
            "content_digest": node["content_digest"],
        }
        for identity, node in nodes.items()
        if node["kind"] == "sample"
    ]
    return _result(
        skill_name,
        values,
        scope,
        items,
        {
            "algorithm": "typed-dag-transitive-provenance-v1",
            "topological_order": list(order),
        },
        {"nodes": list(nodes.values()), "edges": edges},
        [
            "The graph validates declared provenance; it does not independently attest source facts.",
            "Only the declared finite graph is covered; no external source discovery or signing.",
        ],
    )


def _revocation(
    skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
) -> Mapping[str, Any]:
    values = _values(payload)
    config = _exact_mapping(values["knowledge object"], "knowledge object", {"revoked_ids"})
    nodes, edges, _, outgoing = _graph(values, scope)
    revoked = [
        require_identifier(item, "revoked_id")
        for item in _sequence(config["revoked_ids"], "revoked_ids", maximum=_MAX_RECORDS)
    ]
    if len(set(revoked)) != len(revoked) or any(identity not in nodes for identity in revoked):
        raise ValueError("revocation contains duplicate or unknown identities")
    if any(nodes[identity]["kind"] not in {"object", "sample", "dataset"} for identity in revoked):
        raise ValueError("revocation roots must be objects, samples or datasets")
    impacts: dict[str, list[str]] = {}
    for identity in sorted(revoked):
        reached = {identity}
        queue = deque([identity])
        while queue:
            for successor in outgoing[queue.popleft()]:
                if successor not in reached:
                    reached.add(successor)
                    queue.append(successor)
        impacts[identity] = sorted(reached)
    affected = set().union(*(set(identities) for identities in impacts.values()))
    items: list[Mapping[str, Any]] = [
        {
            "node_id": identity,
            "kind": nodes[identity]["kind"],
            "content_digest": nodes[identity]["content_digest"],
            "revocation_sources": sorted(
                root for root, descendants in impacts.items() if identity in descendants
            ),
        }
        for identity in sorted(affected)
    ]
    return _result(
        skill_name,
        values,
        scope,
        items,
        {
            "algorithm": "typed-dag-descendant-impact-v1",
            "impact_index": impacts,
            "affected_checkpoint_ids": sorted(
                identity for identity in affected if nodes[identity]["kind"] == "checkpoint"
            ),
            "affected_adapter_ids": sorted(
                identity for identity in affected if nodes[identity]["kind"] == "adapter"
            ),
            "deletion_executed": False,
            "unlearning_executed": False,
            "retraining_executed": False,
        },
        {"nodes": list(nodes.values()), "edges": edges},
        [
            "Impact is complete only for the supplied graph, whose provenance remains unverified.",
            "This is an impact index; deletion, model unlearning and retraining require external execution.",
        ],
    )


def _preference(
    skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
) -> Mapping[str, Any]:
    values = _values(payload, preference=True)
    episode = _exact_mapping(values["experience episode"], "experience episode", {"candidates"})
    _experience_binding(values)
    candidates = _unique_records(
        episode["candidates"],
        "candidates",
        {
            "candidate_id",
            "task_id",
            "prompt_digest",
            "content_digest",
            "tenant_id",
            "project_id",
        },
        "candidate_id",
    )
    for candidate in candidates.values():
        _scope_record(candidate, scope)
        require_identifier(candidate["task_id"], "task_id")
        validate_digest(candidate["prompt_digest"])
        validate_digest(candidate["content_digest"])
    evidence = _exact_mapping(values["verification evidence"], "verification evidence", {"results"})
    results = _unique_records(
        evidence["results"],
        "results",
        {
            "candidate_id",
            "content_digest",
            "checks",
        },
        "candidate_id",
    )
    if set(results) != set(candidates):
        raise ValueError("preference verification must cover exactly the candidates")
    verdicts: dict[str, bool] = {}
    for identity, result in results.items():
        if result["content_digest"] != candidates[identity]["content_digest"]:
            raise ValueError("verification candidate content binding mismatch")
        checks = _unique_records(result["checks"], "checks", {"check_id", "status"}, "check_id")
        if any(
            require_identifier(check["status"], "check status") not in {"PASS", "FAIL"}
            for check in checks.values()
        ):
            raise ValueError("preference verification has an unresolved check")
        verdicts[identity] = all(check["status"] == "PASS" for check in checks.values())
    feedback = _exact_mapping(values["human feedback"], "human feedback", {"decisions"})
    decisions = _unique_records(
        feedback["decisions"],
        "decisions",
        {
            "decision_id",
            "actor_id",
            "task_id",
            "chosen_id",
            "rejected_id",
            "reason",
            "chosen_evidence_digest",
            "rejected_evidence_digest",
        },
        "decision_id",
    )
    items: list[Mapping[str, Any]] = []
    pairs: set[tuple[str, str]] = set()
    roles: dict[tuple[str, str], str] = {}
    for decision in decisions.values():
        require_identifier(decision["actor_id"], "actor_id")
        task = require_identifier(decision["task_id"], "task_id")
        chosen_id = require_identifier(decision["chosen_id"], "chosen_id")
        rejected_id = require_identifier(decision["rejected_id"], "rejected_id")
        if chosen_id not in candidates or rejected_id not in candidates or chosen_id == rejected_id:
            raise ValueError("preference roles must reference two distinct candidates")
        chosen, rejected = candidates[chosen_id], candidates[rejected_id]
        if (
            task != chosen["task_id"]
            or task != rejected["task_id"]
            or chosen["prompt_digest"] != rejected["prompt_digest"]
        ):
            raise ValueError("preference pair must share its exact task and prompt")
        if chosen["content_digest"] == rejected["content_digest"]:
            raise ValueError("preference pair cannot contain identical content")
        if require_identifier(decision["reason"], "reason") not in {
            "accepted-over-failed",
            "repair-over-failed",
            "rollback-of-failed",
        }:
            raise ValueError("unsupported preference evidence reason")
        if {check["check_id"] for check in results[chosen_id]["checks"]} != {
            check["check_id"] for check in results[rejected_id]["checks"]
        }:
            raise ValueError("preference candidates must use the same declared check suite")
        if not verdicts[chosen_id] or verdicts[rejected_id]:
            raise ValueError("chosen must pass all checks and rejected must have a failing check")
        for identity, role in ((chosen_id, "chosen"), (rejected_id, "rejected")):
            if decision[f"{role}_evidence_digest"] != canonical_digest(results[identity]):
                raise ValueError("preference evidence digest mismatch")
            if roles.get((task, identity), role) != role:
                raise ValueError("preference decisions contain conflicting roles")
            roles[(task, identity)] = role
        if (chosen_id, rejected_id) in pairs:
            raise ValueError("duplicate preference pair")
        pairs.add((chosen_id, rejected_id))
        items.append(
            {
                "pair_id": "pair-" + canonical_digest(decision)[7:39],
                "task_id": task,
                "chosen_id": chosen_id,
                "rejected_id": rejected_id,
                "chosen_digest": chosen["content_digest"],
                "rejected_digest": rejected["content_digest"],
                "decision_digest": canonical_digest(decision),
            }
        )
    return _result(
        skill_name,
        values,
        scope,
        items,
        {
            "algorithm": "task-prompt-content-evidence-bound-pairs-v1",
            "human_identity_verified": False,
            "independent_verification": "NOT_RUN",
        },
        {
            "candidate_ids": sorted(candidates),
            "evidence_digests": {
                identity: canonical_digest(result) for identity, result in results.items()
            },
        },
        [
            "Input check results and human decisions are structurally bound, not independently verified.",
            "Only passing-versus-failing candidates are supported; subjective ranking is unsupported.",
            "Human identity, consent and evidence authenticity require trusted external verification.",
        ],
    )


def _selection(
    skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
) -> Mapping[str, Any]:
    values = _values(payload)
    episode = _exact_mapping(values["experience episode"], "experience episode", {"samples"})
    config = _exact_mapping(
        values["knowledge object"], "knowledge object", {"weights", "budget_units", "limit"}
    )
    weights_raw = _exact_mapping(config["weights"], "weights", _METRICS)
    weights: dict[str, Fraction] = {}
    for metric in sorted(_METRICS):
        value = _number(weights_raw[metric], metric)
        if not 0 <= value <= 1:
            raise ValueError("selection weights must be normalized to [0,1]")
        weights[metric] = Fraction(str(value))
    if sum(weights.values()) != 1:
        raise ValueError("selection weights must sum exactly to one")
    budget = _integer(config["budget_units"], "budget_units")
    limit = _integer(config["limit"], "limit", maximum=_MAX_RECORDS)
    samples = _unique_records(
        episode["samples"],
        "samples",
        {
            "sample_id",
            "tenant_id",
            "project_id",
            "content_digest",
            "metrics",
            "cost_units",
        },
        "sample_id",
    )
    scores: dict[str, Fraction] = {}
    costs: dict[str, int] = {}
    for identity, sample in samples.items():
        _scope_record(sample, scope)
        validate_digest(sample["content_digest"])
        metrics = _exact_mapping(sample["metrics"], "metrics", _METRICS)
        score = Fraction(0)
        for metric in sorted(_METRICS):
            value = _number(metrics[metric], metric)
            if not 0 <= value <= 1:
                raise ValueError("selection metrics must be normalized to [0,1]")
            score += weights[metric] * Fraction(str(value))
        scores[identity] = score
        costs[identity] = _integer(sample["cost_units"], "cost_units", minimum=1)
    ranking = sorted(samples, key=lambda identity: (-scores[identity], identity))
    remaining = budget
    items: list[Mapping[str, Any]] = []
    excluded: list[Mapping[str, Any]] = []
    for identity in ranking:
        score = scores[identity]
        if len(items) >= limit or costs[identity] > remaining:
            excluded.append(
                {"sample_id": identity, "reason": "limit" if len(items) >= limit else "budget"}
            )
            continue
        remaining -= costs[identity]
        items.append(
            {
                "sample_id": identity,
                "content_digest": samples[identity]["content_digest"],
                "score": float(score),
                "score_fraction": f"{score.numerator}/{score.denominator}",
                "cost_units": costs[identity],
            }
        )
    return _result(
        skill_name,
        values,
        scope,
        items,
        {
            "algorithm": "weighted-score-greedy-with-skip-v1",
            "ranking": ranking,
            "budget_units": budget,
            "used_units": budget - remaining,
            "remaining_units": remaining,
            "excluded": excluded,
        },
        {"sample_ids": sorted(samples)},
        [
            "Caller-supplied normalized metrics are not measured or independently calibrated here.",
            "Greedy score ordering respects the budget; it does not claim optimal knapsack selection.",
            "Selection creates an annotation queue only; no label, training or provider call is executed.",
        ],
    )


def _deduplicate(
    skill_name: str, payload: Mapping[str, Any], scope: TenantScope, invocation_id: str
) -> Mapping[str, Any]:
    values = _values(payload)
    episode = _exact_mapping(values["experience episode"], "experience episode", {"samples"})
    config = _exact_mapping(values["knowledge object"], "knowledge object", {"language"})
    if config["language"] != "python":
        raise ValueError("AST deduplication supports only the local Python grammar")
    samples = _unique_records(
        episode["samples"],
        "samples",
        {
            "sample_id",
            "tenant_id",
            "project_id",
            "source",
        },
        "sample_id",
    )
    fingerprints: dict[str, list[str]] = defaultdict(list)
    source_digests: dict[str, str] = {}
    total_nodes = 0
    for identity, sample in samples.items():
        _scope_record(sample, scope)
        source = _text(sample["source"], "source", maximum=32_768)
        try:
            tree = ast.parse(source, mode="exec", type_comments=True)
        except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
            raise ValueError("source is outside the bounded Python AST parser") from exc
        queue: deque[tuple[ast.AST, int]] = deque([(tree, 0)])
        nodes = 0
        while queue:
            node, depth = queue.popleft()
            nodes += 1
            total_nodes += 1
            if depth > 64 or nodes > 10_000 or total_nodes > 50_000:
                raise ValueError("Python AST exceeds its node/depth budget")
            queue.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
        try:
            normalized = ast.dump(tree, annotate_fields=True, include_attributes=False)
        except RecursionError as exc:
            raise ValueError("Python AST exceeds the serialization budget") from exc
        fingerprint = canonical_digest({"language": "python", "ast": normalized})
        fingerprints[fingerprint].append(identity)
        source_digests[identity] = canonical_digest(source)
    items: list[Mapping[str, Any]] = []
    groups: list[Mapping[str, Any]] = []
    for fingerprint, members in sorted(fingerprints.items()):
        representative = min(members)
        groups.append(
            {
                "fingerprint": fingerprint,
                "representative_id": representative,
                "sample_ids": sorted(members),
            }
        )
        items.append(
            {
                "sample_id": representative,
                "content_digest": source_digests[representative],
                "ast_fingerprint": fingerprint,
                "duplicate_ids": sorted(set(members) - {representative}),
            }
        )
    return _result(
        skill_name,
        values,
        scope,
        sorted(items, key=lambda item: str(item["sample_id"])),
        {
            "algorithm": "python-ast-exact-structure-v1",
            "parser_version": sys.version.split()[0],
            "source_count": len(samples),
            "unique_count": len(items),
            "duplicate_count": len(samples) - len(items),
            "groups": groups,
            "source_executed": False,
            "behavioral_equivalence_proven": False,
        },
        {"source_digests": source_digests, "groups": groups},
        [
            "Only Python AST structure is compared; identifiers, literals and type comments are retained.",
            "Formatting and ordinary comments are ignored; graph, behavior and near-duplicate matching are unsupported.",
            "AST equality is not behavioral equivalence: source positions, comments and formatting can be observable.",
            "Source is parsed and bounded, never imported, compiled or executed.",
        ],
    )


def build_dataset_handlers(
    catalog: CatalogView, store: FoundryStore | None
) -> dict[str, LocalHandler]:
    """Return exact pure handlers; the outer host runtime enforces authority."""
    missing = DATASET_SEMANTIC_SKILLS - set(catalog.atomic_skills)
    if missing:
        raise ValueError(
            f"dataset semantic Skills absent from the exact catalog: {sorted(missing)}"
        )
    return {
        "repo-org-time-split-builder": _split,
        "dataset-lineage-and-provenance": _lineage,
        "dataset-revocation-unlearning-index": _revocation,
        "preference-pair-builder": _preference,
        "active-learning-sample-selection": _selection,
        "semantic-and-ast-deduplication": _deduplicate,
    }
