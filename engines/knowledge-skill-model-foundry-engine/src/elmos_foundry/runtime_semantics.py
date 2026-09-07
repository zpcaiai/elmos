"""Two bounded bootstrap operations: local compensation and scoped lexical retrieval.

The host authenticates the scope before calling these handlers. Caller documents
are untrusted data and cannot grant rights. Transactions affect only their private
Foundry checkpoint; no application, repository, command, or provider is executed.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import re
from typing import Any

from .canonical import (
    canonical_digest,
    canonical_json_bytes,
    canonical_value,
    require_identifier,
    validate_digest,
)
from .domain import TenantScope
from .local_semantics import (
    CatalogView,
    LocalHandler,
    _exact_mapping,
    _mapping,
    _response,
    _sequence,
    _text,
)
from .store import FoundryStore, RunState, StoreError


RUNTIME_SEMANTIC_SKILLS = frozenset({
    "skill-transaction-and-rollback", "tenant-policy-aware-retrieval",
})
RETRIEVAL_CAPABILITIES = (
    "foundry.retrieval.classification.internal",
    "foundry.retrieval.read",
    "foundry.retrieval.region.local",
    "foundry.retrieval.rights.internal",
    "foundry.retrieval.role.reader",
)
_TRANSACTION_INPUTS = {"runbook", "experience episodes", "task contract", "semantic IR", "policy context"}
_RETRIEVAL_INPUTS = {"task contract", "semantic graph", "knowledge objects", "token budget", "policy context"}


def _integer(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be an integer in {minimum}..{maximum}")
    return int(value)


def _strings(value: Any, label: str, *, minimum: int = 1, maximum: int = 128) -> list[str]:
    items = [require_identifier(item, label) for item in _sequence(
        value, label, minimum=minimum, maximum=maximum,
    )]
    if len(items) != len(set(items)):
        raise ValueError(f"{label} contains duplicate entries")
    return items


def _values(payload: Mapping[str, Any], keys: set[str]) -> Mapping[str, Any]:
    values = _exact_mapping(payload.get("inputs"), "inputs", keys)
    canonical_value(values)
    return values


def _scope_binding(scope: TenantScope) -> Mapping[str, str]:
    # Lease/invocation identities may change on replay; the subject, purpose,
    # environment and exact workspace/revision cannot.
    return {key: str(getattr(scope, key)) for key in (
        "tenant_id", "project_id", "actor_id", "environment_id", "workspace_digest",
        "revision_set_id", "purpose",
    )}


def _local_mutations(
    before: Mapping[str, Any], operations: Any,
) -> tuple[dict[str, Any], dict[str, Any], list[Mapping[str, Any]]]:
    state = dict(before)
    inverses: list[Mapping[str, Any]] = []
    for raw in _sequence(operations, "operations", maximum=64):
        operation = _exact_mapping(raw, "operation", {
            "op", "key", "expected_present", "expected_digest", "value",
        })
        key = require_identifier(operation["key"], "operation.key")
        expected_present = operation["expected_present"]
        if not isinstance(expected_present, bool):
            raise ValueError("expected_present must be boolean")
        present = key in state
        if expected_present != present:
            raise ValueError("local state presence precondition does not match")
        if expected_present:
            validate_digest(operation["expected_digest"], "operation.expected_digest")
            if canonical_digest(state[key]) != operation["expected_digest"]:
                raise ValueError("local state digest precondition does not match")
        elif operation["expected_digest"] is not None:
            raise ValueError("absent state must not declare an expected digest")
        inverses.append({"key": key, "restore_present": present, "restore_value": state.get(key)})
        if operation["op"] == "set":
            state[key] = canonical_value(operation["value"])
        elif operation["op"] == "delete":
            if not present or operation["value"] is not None:
                raise ValueError("delete requires existing state and null value")
            del state[key]
        else:
            raise ValueError("unsupported operation; only local set/delete are implemented")
    restored = dict(state)
    for inverse in reversed(inverses):
        if inverse["restore_present"]:
            restored[str(inverse["key"])] = inverse["restore_value"]
        else:
            restored.pop(str(inverse["key"]), None)
    if canonical_digest(restored) != canonical_digest(before):
        raise StoreError("local compensation did not restore the exact checkpoint")
    return state, restored, list(reversed(inverses))


class RuntimeSemantics:
    def __init__(self, catalog: CatalogView, store: FoundryStore | None) -> None:
        self.catalog = catalog
        self.store = store

    def skill_transaction_and_rollback(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        if self.store is None:
            raise StoreError("local transaction requires the trusted durable Foundry store")
        values = _values(payload, _TRANSACTION_INPUTS)
        runbook = _exact_mapping(values["runbook"], "runbook", {"transaction_id", "mode"})
        transaction_id = require_identifier(runbook["transaction_id"], "transaction_id")
        mode = runbook["mode"]
        if mode not in {"commit", "rollback-rehearsal"}:
            raise ValueError("transaction mode must be commit or rollback-rehearsal")
        task = _exact_mapping(values["task contract"], "task contract", {"purpose", "snapshot"})
        if task["purpose"] != scope.purpose:
            raise ValueError("transaction purpose differs from the trusted scope")
        before = _mapping(task["snapshot"], "snapshot")
        if len(canonical_json_bytes(before)) > 65_536:
            raise ValueError("local transaction snapshot exceeds 64 KiB")
        for key in before:
            require_identifier(key, "snapshot.key")
        ir = _exact_mapping(values["semantic IR"], "semantic IR", {"operations"})
        policy = _exact_mapping(values["policy context"], "policy context", {"effect_class"})
        if policy["effect_class"] != "LOCAL_DETERMINISTIC":
            raise ValueError("transaction does not authorize external effects")
        episodes = _exact_mapping(values["experience episodes"], "experience episodes", {"episode_ids"})
        _strings(episodes["episode_ids"], "episode_ids", minimum=0)
        after, restored, inverses = _local_mutations(before, ir["operations"])
        if len(canonical_json_bytes(after)) > 65_536:
            raise ValueError("local transaction result exceeds 64 KiB")
        binding = _scope_binding(scope)
        request = {"scope": binding, "inputs": values}
        decision = self.store.begin_run(
            scope, "foundry.local-compensating-transaction", transaction_id, request,
            run_id="tx-" + canonical_digest({"scope": binding, "transaction_id": transaction_id})[7:39],
        )
        run = decision.record
        if decision.replayed:
            if run.state == RunState.SUCCEEDED and run.response is not None:
                return run.response
            raise StoreError("transaction is incomplete; durable reconciliation is required before retry")
        self.store.transition_run(
            scope, run.run_id, RunState.PENDING, RunState.RUNNING, reason="local-transaction-started",
        )
        committed = after if mode == "commit" else restored
        checkpoint = self.store.append_checkpoint(
            scope, run.run_id, 0,
            {
                "scope": binding, "request_digest": run.request_digest,
                "before": before, "after": committed,
                "forward_state_digest": canonical_digest(after),
                "compensations": inverses,
                "local_rollback_verified": True,
                "transaction_state": "COMMITTED" if mode == "commit" else "COMPENSATED",
                "external_effects_executed": False,
            },
            checkpoint_id=run.run_id + "-checkpoint",
        )
        primary = {
            "transaction_id": transaction_id, "run_id": run.run_id,
            "state": "COMMITTED" if mode == "commit" else "COMPENSATED",
            "snapshot": canonical_value(committed),
            "before_digest": canonical_digest(before), "after_digest": canonical_digest(committed),
            "forward_state_digest": canonical_digest(after),
            "checkpoint_digest": checkpoint.checkpoint_digest,
            "compensation_order": [item["key"] for item in inverses],
            "local_rollback_verified": True,
            "external_effects_executed": False, "external_rollback_status": "NOT_RUN",
        }
        result = _response({
            "skill package": primary,
            "activation rules": {"effect_class": "LOCAL_DETERMINISTIC", "scope": binding},
            "workflow DAG": {
                "skill": skill, "steps": ["snapshot", "local-mutations", "compensation-replay", "durable-checkpoint"],
                "dependencies": list(self.catalog.atomic_skills[skill]["dependencies"]),
            },
            "evidence bundle": {
                "input_digest": canonical_digest(values), "checkpoint_digest": checkpoint.checkpoint_digest,
                "local_rollback_verified": True, "independent_verification": "NOT_RUN",
                "external_evidence_status": "NOT_RUN", "certification_status": "NOT_CERTIFIED",
            },
        })
        self.store.transition_run(
            scope, run.run_id, RunState.RUNNING, RunState.SUCCEEDED,
            reason="local-checkpoint-and-compensation-verified", response=result,
        )
        return result

    def tenant_policy_aware_retrieval(
        self, skill: str, payload: Mapping[str, Any], scope: TenantScope, invocation: str,
    ) -> Mapping[str, Any]:
        values = _values(payload, _RETRIEVAL_INPUTS)
        task = _exact_mapping(values["task contract"], "task contract", {"query", "version"})
        query = _text(task["query"], "query", maximum=512)
        version = require_identifier(task["version"], "version")
        terms = set(re.findall(r"[^\W_]+", query.casefold()))
        if not 1 <= len(terms) <= 32:
            raise ValueError("query must contain 1..32 lexical terms")
        policy = _exact_mapping(values["policy context"], "policy context", {"purpose", "permitted_capabilities"})
        if policy["purpose"] != scope.purpose:
            raise ValueError("retrieval purpose differs from the trusted scope")
        requested = set(_strings(policy["permitted_capabilities"], "permitted_capabilities", minimum=0))
        granted = requested.intersection(scope.capabilities)
        budget = _exact_mapping(values["token budget"], "token budget", {"max_utf8_bytes", "max_items"})
        max_bytes = _integer(budget["max_utf8_bytes"], "max_utf8_bytes", 512, 262_144)
        max_items = _integer(budget["max_items"], "max_items", 1, 32)
        graph = _exact_mapping(values["semantic graph"], "semantic graph", {"document_ids"})
        selected_ids = set(_strings(graph["document_ids"], "document_ids", minimum=0))
        documents: dict[str, Mapping[str, Any]] = {}
        for raw in _sequence(values["knowledge objects"], "knowledge objects", minimum=0, maximum=128):
            document = _exact_mapping(raw, "knowledge object", {
                "id", "tenant_id", "project_id", "revision_set_id", "version", "content",
                "content_digest", "source_id", "region", "classification", "required_roles",
                "rights_class", "purposes",
            })
            identity = require_identifier(document["id"], "document.id")
            if identity in documents:
                raise ValueError("duplicate knowledge object identity")
            for key in ("tenant_id", "project_id", "version", "source_id", "region", "classification", "rights_class"):
                require_identifier(document[key], f"document.{key}")
            _text(document["content"], "document.content", maximum=16_384)
            validate_digest(document["content_digest"], "content_digest")
            validate_digest(document["revision_set_id"], "revision_set_id")
            if document["content_digest"] != canonical_digest(document["content"]):
                raise ValueError("document content digest mismatch")
            _strings(document["required_roles"], "required_roles", maximum=16)
            _strings(document["purposes"], "purposes", maximum=16)
            documents[identity] = document
        if selected_ids - set(documents):
            raise ValueError("semantic graph references unknown documents")
        candidates: list[tuple[int, str, Mapping[str, Any]]] = []
        excluded: Counter[str] = Counter()
        for identity, document in sorted(documents.items()):
            required = {
                "foundry.retrieval.read",
                f"foundry.retrieval.region.{document['region']}",
                f"foundry.retrieval.classification.{document['classification']}",
                f"foundry.retrieval.rights.{document['rights_class']}",
                *(f"foundry.retrieval.role.{role}" for role in document["required_roles"]),
            }
            reason = None
            if (document["tenant_id"], document["project_id"]) != (scope.tenant_id, scope.project_id):
                reason = "tenant-or-project-mismatch"
            elif scope.purpose not in document["purposes"]:
                reason = "purpose-not-permitted"
            elif document["revision_set_id"] != scope.revision_set_id or document["version"] != version:
                reason = "revision-or-version-mismatch"
            elif not required.issubset(granted):
                reason = "trusted-capability-missing"
            elif selected_ids and identity not in selected_ids:
                reason = "outside-semantic-graph"
            if reason is not None:
                excluded[reason] += 1
                continue
            frequencies = Counter(re.findall(r"[^\W_]+", str(document["content"]).casefold()))
            score = sum(min(frequencies[term], 16) for term in terms)
            if score == 0:
                excluded["no-lexical-match"] += 1
                continue
            candidates.append((score, identity, document))
        candidates.sort(key=lambda item: (-item[0], item[1]))
        context: dict[str, Any] = {"documents": [], "content_trust": "untrusted-caller-data"}
        ranked: list[Mapping[str, Any]] = []
        citations: list[Mapping[str, Any]] = []
        for score, identity, document in candidates:
            if len(ranked) >= max_items:
                excluded["item-budget"] += 1
                continue
            item = {"id": identity, "content": document["content"], "content_digest": document["content_digest"]}
            proposed = {**context, "documents": [*context["documents"], item]}
            if len(canonical_json_bytes(proposed)) > max_bytes:
                excluded["byte-budget"] += 1
                continue
            context = proposed
            ranked.append({"id": identity, "lexical_score": score, "content_digest": document["content_digest"]})
            citations.append({"id": identity, "source_id": document["source_id"], "content_digest": document["content_digest"]})
        return _response({
            "ranked evidence": {"items": ranked, "status": "CANDIDATES" if ranked else "ABSTAINED"},
            "context package": context,
            "citation map": {"entries": citations, "provenance_status": "CALLER_DECLARED_DIGEST_CHECKED"},
            "retrieval trace": {
                "input_count": len(documents), "selected_count": len(ranked),
                "excluded_reason_counts": dict(sorted(excluded.items())),
                "effective_capabilities": sorted(granted),
                "context_utf8_bytes": len(canonical_json_bytes(context)), "max_utf8_bytes": max_bytes,
                "budget_unit": "UTF8_BYTES", "model_token_count": "NOT_RUN",
                "instruction_authority": "NONE", "scope": _scope_binding(scope),
                "input_digest": canonical_digest(values), "vector_and_reranker_execution": "NOT_RUN",
                "external_evidence_status": "NOT_RUN", "independent_verification": "NOT_RUN",
            },
        })


def build_runtime_handlers(catalog: CatalogView, store: FoundryStore | None) -> dict[str, LocalHandler]:
    missing = RUNTIME_SEMANTIC_SKILLS - set(catalog.atomic_skills)
    if missing:
        raise ValueError(f"runtime semantic Skills absent from the exact catalog: {sorted(missing)}")
    runtime = RuntimeSemantics(catalog, store)
    return {
        "skill-transaction-and-rollback": runtime.skill_transaction_and_rollback,
        "tenant-policy-aware-retrieval": runtime.tenant_policy_aware_retrieval,
    }
