from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sqlite3
from collections.abc import Iterator, Mapping
from copy import deepcopy
from pathlib import Path

import pytest

import elmos_commercial_expansion as public_package
import elmos_commercial_expansion.store as store_module
from elmos_commercial_expansion.artifacts import ContentAddressedArtifactStore
from elmos_commercial_expansion.authority import (
    HMACAuthorityVerifier,
    LocalHMACAuthoritySigner,
)
from elmos_commercial_expansion.canonical import (
    JSONLimits,
    canonical_json,
    canonical_json_bytes,
    digest_object,
    strict_json_loads,
    to_jsonable,
)
from elmos_commercial_expansion.cli import _check_store, _gate
from elmos_commercial_expansion.contracts import (
    CapabilityLease,
    Evidence,
    EvidenceStatus,
    GateLevel,
    HandlerRequest,
    Invocation,
    Obligation,
    PolicyDecision,
    PolicyEffect,
    Scope,
    utc_now,
    validate_handler_inputs,
)
from elmos_commercial_expansion.errors import (
    AuthorizationError,
    ContractError,
    IdempotencyConflict,
    IntegrityError,
    NotFoundError,
    StoreError,
    TransitionConflict,
)
from elmos_commercial_expansion.gate import E0E5Gate
from elmos_commercial_expansion.kernels import _exact_registry
from elmos_commercial_expansion.runtime import CommercialCapabilityRuntime
from elmos_commercial_expansion.service import (
    CommercialCapabilityExpansionService,
    _projection_status,
    get_commercial_status,
    list_capability_kernels,
)
from elmos_commercial_expansion.store import ReadonlyControlPlaneStore, SQLiteControlPlaneStore

SKILL_ID = "universal-agent-skill-runtime"
KEYS = {"test-key": b"k" * 32}
_CATALOG_RELATIVE = Path("docs/commercial-capability-expansion/COMPILED_SKILL_CATALOG.json")
_RECEIPT_RELATIVE = Path("docs/commercial-capability-expansion/QUALIFICATION_RECEIPT.json")
_WORKSPACE_SKILLS_RELATIVE = Path(".agents/skills")
_RUNTIME_SKILLS_RELATIVE = Path("agent-skills/runtime")
_MASTER_SKILL_ID = "elmos-commercial-capability-expansion"
_WRAPPER_FILES = ("SKILL.md", "compiled-contract.json", "agents/openai.yaml")


@pytest.fixture
def scope() -> Scope:
    return Scope(
        tenant_id="tenant-a",
        project_id="project-a",
        actor_id="actor-a",
        revision=digest_object({"commit": "abc123"}, domain="revision"),
    )


@pytest.fixture
def verifier() -> HMACAuthorityVerifier:
    return HMACAuthorityVerifier(KEYS)


@pytest.fixture
def signer() -> LocalHMACAuthoritySigner:
    return LocalHMACAuthoritySigner(KEYS)


@pytest.fixture
def runtime_parts(tmp_path: Path, verifier: HMACAuthorityVerifier):
    store = SQLiteControlPlaneStore(tmp_path / "state" / "runtime.sqlite3")
    artifact_store = ContentAddressedArtifactStore(tmp_path / "artifacts")
    runtime = CommercialCapabilityRuntime(
        store=store,
        artifact_store=artifact_store,
        authority_verifier=verifier,
    )
    yield runtime, store, artifact_store
    store.close()


def _inputs(policy: str = "local") -> dict[str, object]:
    return {
        "requested_skills": ["repository-semantic-code-graph"],
        "policy": {"mode": policy},
    }


def _authority(
    runtime: CommercialCapabilityRuntime,
    signer: LocalHMACAuthoritySigner,
    scope: Scope,
    *,
    inputs: dict[str, object] | None = None,
    key: str = "idem-1",
    skill_id: str = SKILL_ID,
    action: str = "plan",
    secret_refs: frozenset[str] = frozenset(),
) -> tuple[Invocation, PolicyDecision, CapabilityLease, object, dict[str, object]]:
    values = _inputs() if inputs is None else inputs
    invocation = runtime.prepare_invocation(
        scope=scope,
        skill_id=skill_id,
        action=action,
        inputs=values,
        idempotency_key=key,
    )
    decision = PolicyDecision(
        decision_id=f"decision-{key}",
        invocation_id=invocation.invocation_id,
        scope_digest=scope.digest,
        skill_id=invocation.skill_id,
        action=invocation.action,
        effect=PolicyEffect.ALLOW,
        policy_revision=digest_object({"policy": "test", "key": key}, domain="policy"),
        decided_at=invocation.issued_at,
        expires_at=invocation.expires_at,
    )
    lease = CapabilityLease(
        lease_id=f"lease-{key}",
        invocation_id=invocation.invocation_id,
        scope=scope,
        skill_id=invocation.skill_id,
        action=invocation.action,
        request_digest=invocation.request_digest,
        policy_decision_id=decision.decision_id,
        policy_decision_digest=decision.digest,
        issued_at=invocation.issued_at,
        expires_at=invocation.expires_at,
        secret_refs=secret_refs,
    )
    proof = signer.mint_proof("test-key", invocation, decision, lease)
    return invocation, decision, lease, proof, values


def _execute(runtime: CommercialCapabilityRuntime, bundle):
    invocation, decision, lease, proof, inputs = bundle
    return runtime.execute(
        invocation,
        inputs=inputs,
        decision=decision,
        lease=lease,
        authority_proof=proof,
    )


def _all_files(root: Path) -> bytes:
    chunks: list[bytes] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        chunks.append(path.read_bytes())
    return b"\n".join(chunks)


def _fixed_digest(character: str) -> str:
    return "sha256:" + character * 64


def _restore_journal_trigger(store: SQLiteControlPlaneStore, operation: str) -> None:
    statements = {
        "UPDATE": """
            CREATE TRIGGER journal_entries_immutable_update
            BEFORE UPDATE ON journal_entries BEGIN
              SELECT RAISE(ABORT, 'append-only journal');
            END
        """,
        "DELETE": """
            CREATE TRIGGER journal_entries_immutable_delete
            BEFORE DELETE ON journal_entries BEGIN
              SELECT RAISE(ABORT, 'append-only journal');
            END
        """,
    }
    store._connection.execute(statements[operation])


def _repository_root_for_tests() -> Path:
    return Path(__file__).absolute().parents[3]


def _projection_tree_digest(files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    digest.update(b"elmos-tree-sha256-v1\0")
    for relative in sorted(files):
        encoded = relative.encode("utf-8")
        content = files[relative]
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _copy_projection(destination: Path) -> tuple[str, ...]:
    repository = _repository_root_for_tests()
    handlers, _ = _exact_registry()
    registry_ids = tuple(sorted(handlers))
    for relative in (_CATALOG_RELATIVE, _RECEIPT_RELATIVE):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository / relative, target)
    for root in (_WORKSPACE_SKILLS_RELATIVE, _RUNTIME_SKILLS_RELATIVE):
        for skill_id in (_MASTER_SKILL_ID, *registry_ids):
            shutil.copytree(repository / root / skill_id, destination / root / skill_id)
    return registry_ids


def _rewrite_json(path: Path, document: object) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _wrapper_payloads(repository: Path, registry_ids: tuple[str, ...]) -> dict[str, bytes]:
    return {
        f"{skill_id}/{relative_name}": (
            repository / _WORKSPACE_SKILLS_RELATIVE / skill_id / relative_name
        ).read_bytes()
        for skill_id in (_MASTER_SKILL_ID, *registry_ids)
        for relative_name in _WRAPPER_FILES
    }


def _bounded_algorithm_cases(scope: Scope) -> list[dict[str, object]]:
    graph = {
        "nodes": ["api", "service", "database", "events"],
        "edges": [
            {"source": "api", "target": "service"},
            {"source": "service", "target": "database"},
            {"source": "service", "target": "events"},
        ],
    }
    snapshot = {"revision_digest": _fixed_digest("a"), "file_count": 4}
    progressive = {
        "skill_metadata": [
            {
                "id": "db-small",
                "summary": "database migration",
                "tags": ["database"],
                "token_budget": 3,
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "environment": scope.environment_id,
                "permissions": ["read"],
            },
            {
                "id": "db-large",
                "summary": "database migration validation",
                "tags": ["database", "migration"],
                "token_budget": 8,
                "tenant_id": scope.tenant_id,
                "project_id": scope.project_id,
                "environment": scope.environment_id,
                "permissions": ["read"],
            },
        ],
        "query_terms": ["database", "migration"],
        "context_token_budget": 8,
        "candidate_permissions": ["read"],
    }
    progressive_reordered = deepcopy(progressive)
    progressive_reordered["skill_metadata"] = list(reversed(progressive["skill_metadata"]))
    progressive_reordered["query_terms"] = ["migration", "database"]
    progressive_invalid = deepcopy(progressive)
    progressive_invalid["skill_metadata"] = [
        progressive["skill_metadata"][0],
        progressive["skill_metadata"][0],
    ]

    provenance = {
        "version_bindings": {"app": "1.0", "lib": "2.0"},
        "source_digests": {"app": _fixed_digest("b"), "lib": _fixed_digest("c")},
        "dependencies": {"app": ["lib"], "lib": []},
    }
    provenance_reordered = {
        "version_bindings": {"lib": "2.0", "app": "1.0"},
        "source_digests": {"lib": _fixed_digest("c"), "app": _fixed_digest("b")},
        "dependencies": {"lib": [], "app": ["lib"]},
    }
    provenance_invalid = {**provenance, "dependencies": {"app": ["lib"], "lib": ["app"]}}

    router = {
        "candidates": [
            {
                "id": "safe",
                "capabilities": ["compile", "test"],
                "cost": "5",
                "latency_ms": 100,
                "quality": "0.9",
                "proof": 4,
                "risk": 5,
            },
            {
                "id": "cheap-unproven",
                "capabilities": ["compile", "test"],
                "cost": "1",
                "latency_ms": 10,
                "quality": "0.99",
                "proof": 1,
                "risk": 1,
            },
        ],
        "constraints": {
            "required_capabilities": ["compile", "test"],
            "max_cost": "10",
            "max_latency_ms": 1_000,
            "min_quality": "0.8",
            "min_proof": 3,
            "max_risk": 20,
        },
    }
    router_reordered = deepcopy(router)
    router_reordered["candidates"] = list(reversed(router["candidates"]))
    router_invalid = deepcopy(router)
    router_invalid["constraints"]["min_proof"] = 5

    cross = {"repository_snapshot": snapshot, "graph": graph, "changed_paths": ["api"]}
    cross_reordered = deepcopy(cross)
    cross_reordered["graph"]["nodes"] = list(reversed(graph["nodes"]))
    cross_reordered["graph"]["edges"] = list(reversed(graph["edges"]))
    cross_invalid = deepcopy(cross)
    cross_invalid["graph"]["edges"].append({"source": "api", "target": "missing"})

    slice_inputs = {
        "repository_snapshot": snapshot,
        "graph": graph,
        "focus_nodes": ["api"],
        "node_costs": {"api": 1, "service": 2, "database": 2, "events": 1},
        "token_budget": 6,
    }
    slice_reordered = deepcopy(slice_inputs)
    slice_reordered["graph"]["nodes"] = list(reversed(graph["nodes"]))
    slice_reordered["graph"]["edges"] = list(reversed(graph["edges"]))
    slice_reordered["node_costs"] = dict(reversed(tuple(slice_inputs["node_costs"].items())))
    slice_invalid = {**slice_inputs, "token_budget": 5}

    affected = {
        "repository_snapshot": snapshot,
        "graph": graph,
        "changed_paths": ["api"],
        "test_coverage": {
            "api": ["test-api"],
            "service": ["test-service"],
            "database": [],
            "events": ["test-events"],
        },
        "critical_nodes": ["database"],
    }
    affected_reordered = deepcopy(affected)
    affected_reordered["graph"]["nodes"] = list(reversed(graph["nodes"]))
    affected_reordered["graph"]["edges"] = list(reversed(graph["edges"]))
    affected_reordered["test_coverage"] = dict(reversed(tuple(affected["test_coverage"].items())))
    affected_invalid = {**affected, "test_coverage": {"missing": ["test-missing"]}}

    risk = {
        "repository_snapshot": snapshot,
        "graph": graph,
        "changed_paths": ["api"],
        "critical_nodes": ["database"],
        "runtime_hot_paths": ["service"],
        "security_boundaries": ["api"],
        "historical_failures": 2,
        "proof_coverage": "0.5",
    }
    risk_reordered = deepcopy(risk)
    risk_reordered["graph"]["nodes"] = list(reversed(graph["nodes"]))
    risk_reordered["graph"]["edges"] = list(reversed(graph["edges"]))
    risk_invalid = {**risk, "critical_nodes": ["outside"]}

    ledger_edits = [
        {
            "sequence": 0,
            "edit_id": "edit-a",
            "path_digest": _fixed_digest("1"),
            "before_digest": _fixed_digest("2"),
            "after_digest": _fixed_digest("3"),
            "rule_id": "rule-a",
            "reason": "preserve behavior",
            "source_evidence_digests": [_fixed_digest("4")],
            "assumptions": ["exact source version"],
            "validation_digests": [_fixed_digest("5")],
            "rollback_digest": _fixed_digest("6"),
        },
        {
            "sequence": 1,
            "edit_id": "edit-b",
            "path_digest": _fixed_digest("7"),
            "before_digest": _fixed_digest("8"),
            "after_digest": _fixed_digest("9"),
            "rule_id": "rule-b",
            "reason": "preserve contract",
            "source_evidence_digests": [_fixed_digest("a")],
            "assumptions": [],
            "validation_digests": [_fixed_digest("b")],
            "rollback_digest": _fixed_digest("c"),
        },
    ]
    ledger = {"edits": ledger_edits}
    ledger_reordered = {"edits": list(reversed(ledger_edits))}
    ledger_invalid = deepcopy(ledger)
    ledger_invalid["edits"][1]["sequence"] = 3

    lineage = {
        "datasets": [
            {"id": "raw", "kind": "dataset"},
            {"id": "clean", "kind": "dataset"},
            {"id": "report", "kind": "dataset"},
        ],
        "lineage_edges": [
            {"source": "raw", "target": "clean", "kind": "dataset"},
            {"source": "clean", "target": "report", "kind": "dataset"},
        ],
        "changed_entities": ["raw"],
    }
    lineage_reordered = deepcopy(lineage)
    lineage_reordered["datasets"] = list(reversed(lineage["datasets"]))
    lineage_reordered["lineage_edges"] = list(reversed(lineage["lineage_edges"]))
    lineage_invalid = deepcopy(lineage)
    lineage_invalid["lineage_edges"] = [{"source": "raw", "target": "clean", "kind": "table"}]

    reconciliation = {
        "source_rows": [
            {"id": 1, "amount": "1.10", "value": "a"},
            {"id": 2, "amount": "2.20", "value": "b"},
        ],
        "target_rows": [
            {"id": 2, "amount": "2.20", "value": "b"},
            {"id": 1, "amount": "1.10", "value": "a"},
        ],
        "key_fields": ["id"],
        "decimal_fields": ["amount"],
    }
    reconciliation_reordered = deepcopy(reconciliation)
    reconciliation_reordered["source_rows"] = list(reversed(reconciliation["source_rows"]))
    reconciliation_reordered["target_rows"] = list(reversed(reconciliation["target_rows"]))
    reconciliation_invalid = deepcopy(reconciliation)
    reconciliation_invalid["source_rows"] = [{"id": 1, "amount": 1.1}]

    scorecard = {
        "observations": {"quality": "0.9", "coverage": "0.6"},
        "rubric": [
            {"metric": "quality", "weight": "0.7", "minimum": "0.8", "mandatory": True},
            {"metric": "coverage", "weight": "0.3", "minimum": "0.5", "mandatory": False},
        ],
    }
    scorecard_reordered = {
        "observations": {"coverage": "0.6", "quality": "0.9"},
        "rubric": list(reversed(scorecard["rubric"])),
    }
    scorecard_invalid = deepcopy(scorecard)
    scorecard_invalid["rubric"][0]["weight"] = "0.5"

    events = [
        {
            "sequence": 0,
            "event_id": "root",
            "parent_id": None,
            "kind": "start",
            "payload_digest": _fixed_digest("d"),
        },
        {
            "sequence": 1,
            "event_id": "child",
            "parent_id": "root",
            "kind": "tool",
            "payload_digest": _fixed_digest("e"),
        },
    ]
    incident = {"expected_events": events, "observed_events": deepcopy(events)}
    incident_reordered = {
        "expected_events": list(reversed(events)),
        "observed_events": list(reversed(deepcopy(events))),
    }
    incident_invalid = deepcopy(incident)
    incident_invalid["observed_events"][1]["sequence"] = 2

    optimizer = {
        "candidates": [
            {"id": "balanced", "cost": "5", "latency_ms": 50, "quality": "0.9", "proof_satisfied": True},
            {"id": "dominated", "cost": "6", "latency_ms": 60, "quality": "0.8", "proof_satisfied": True},
            {"id": "fast", "cost": "7", "latency_ms": 20, "quality": "0.9", "proof_satisfied": True},
        ],
        "constraints": {
            "max_cost": "10",
            "max_latency_ms": 100,
            "min_quality": "0.8",
            "proof_required": True,
        },
    }
    optimizer_reordered = deepcopy(optimizer)
    optimizer_reordered["candidates"] = list(reversed(optimizer["candidates"]))
    optimizer_invalid = deepcopy(optimizer)
    optimizer_invalid["constraints"]["min_quality"] = "1.1"

    return [
        {"skill": "progressive-skill-disclosure", "inputs": progressive, "reordered": progressive_reordered, "invalid": progressive_invalid, "code": "DUPLICATE_LOCAL_INPUT", "path": ("selected_skill_ids",), "value": ["db-small"]},
        {"skill": "skill-version-provenance", "inputs": provenance, "reordered": provenance_reordered, "invalid": provenance_invalid, "code": "PROVENANCE_CYCLE", "path": ("topological_order",), "value": ["lib", "app"]},
        {"skill": "model-tool-skill-router", "inputs": router, "reordered": router_reordered, "invalid": router_invalid, "code": "NO_FEASIBLE_CANDIDATE", "path": ("selected_id",), "value": "safe"},
        {"skill": "cross-repository-impact-analysis", "inputs": cross, "reordered": cross_reordered, "invalid": cross_invalid, "code": "INVALID_GRAPH", "path": ("affected_count",), "value": 4},
        {"skill": "repository-slicing-context-pack", "inputs": slice_inputs, "reordered": slice_reordered, "invalid": slice_invalid, "code": "SLICE_BUDGET_EXCEEDED", "path": ("used_tokens",), "value": 6},
        {"skill": "affected-test-selection", "inputs": affected, "reordered": affected_reordered, "invalid": affected_invalid, "code": "INVALID_GRAPH", "path": ("confidence",), "value": "INCOMPLETE"},
        {"skill": "change-risk-classifier", "inputs": risk, "reordered": risk_reordered, "invalid": risk_invalid, "code": "INVALID_RISK_INPUT", "path": ("risk", "level"), "value": "MEDIUM"},
        {"skill": "transformation-explainability-ledger", "inputs": ledger, "reordered": ledger_reordered, "invalid": ledger_invalid, "code": "INVALID_LEDGER_SEQUENCE", "path": ("entry_count",), "value": 2},
        {"skill": "data-lineage-impact-analysis", "inputs": lineage, "reordered": lineage_reordered, "invalid": lineage_invalid, "code": "INVALID_LINEAGE", "path": ("affected_consumers",), "value": ["clean", "report"]},
        {"skill": "data-migration-reconciliation", "inputs": reconciliation, "reordered": reconciliation_reordered, "invalid": reconciliation_invalid, "code": "INVALID_RECONCILIATION_ROW", "path": ("equivalent",), "value": True},
        {"skill": "agent-evidence-evaluation", "inputs": scorecard, "reordered": scorecard_reordered, "invalid": scorecard_invalid, "code": "INVALID_RUBRIC", "path": ("decision",), "value": "PASS_BOUNDED_LOCAL"},
        {"skill": "incident-replay-root-cause", "inputs": incident, "reordered": incident_reordered, "invalid": incident_invalid, "code": "INCIDENT_REPLAY_INCONCLUSIVE", "path": ("equivalent",), "value": True},
        {"skill": "cost-latency-quality-optimizer", "inputs": optimizer, "reordered": optimizer_reordered, "invalid": optimizer_invalid, "code": "NO_FEASIBLE_CANDIDATE", "path": ("selected_id",), "value": "balanced"},
    ]


def test_default_authority_is_deny_and_payload_cannot_override_scope(
    tmp_path: Path,
    scope: Scope,
    signer: LocalHMACAuthoritySigner,
):
    store = SQLiteControlPlaneStore(tmp_path / "deny" / "runtime.sqlite3")
    runtime = CommercialCapabilityRuntime(
        store=store,
        artifact_store=ContentAddressedArtifactStore(tmp_path / "deny-artifacts"),
    )
    bundle = _authority(runtime, signer, scope)
    with pytest.raises(AuthorizationError) as denied:
        _execute(runtime, bundle)
    assert denied.value.code == "AUTHORITY_VERIFIER_UNAVAILABLE"
    assert store.verify_all_integrity()["scope_count"] == 0

    with pytest.raises(AuthorizationError) as override:
        runtime.prepare_invocation(
            scope=scope,
            skill_id=SKILL_ID,
            action="plan",
            inputs={"tenant_id": "tenant-evil"},
            idempotency_key="override",
        )
    assert override.value.code == "TRUSTED_SCOPE_OVERRIDE"
    store.close()


def test_exact_execution_is_conservative_idempotent_and_artifact_authorized(
    runtime_parts,
    scope: Scope,
    signer: LocalHMACAuthoritySigner,
):
    runtime, store, artifact_store = runtime_parts
    bundle = _authority(runtime, signer, scope)
    first = _execute(runtime, bundle)
    replay = _execute(runtime, bundle)
    assert first.state == "COMPLETED"
    assert first.outcome == "NOT_RUN"
    assert first.certification_status == "NOT_CERTIFIED"
    assert first.external_evidence_status == "NOT_RUN"
    assert replay.replayed is True
    assert replay.result_digest == first.result_digest
    assert replay.result is not None
    artifact = replay.result["artifacts"][-1]
    payload = runtime.read_artifact(
        bundle[0],
        digest=artifact["digest"],
        decision=bundle[1],
        lease=bundle[2],
        authority_proof=bundle[3],
    )
    assert payload
    assert artifact["uri"].startswith("elmos-cas://scope/")
    assert "file://" not in artifact["uri"]
    assert not hasattr(artifact_store, "get")
    assert not hasattr(artifact_store, "put")
    assert store.verify_all_integrity()["status"] == "OK"


def test_tenant_project_composite_isolation(runtime_parts, scope: Scope, signer):
    runtime, store, _ = runtime_parts
    bundle = _authority(runtime, signer, scope)
    _execute(runtime, bundle)
    other_scope = Scope(
        tenant_id="tenant-b",
        project_id=scope.project_id,
        actor_id=scope.actor_id,
        revision=scope.revision,
    )
    with pytest.raises(NotFoundError):
        store.get_invocation(other_scope, bundle[0].invocation_id)
    assert store.get_invocation(scope, bundle[0].invocation_id).state == "COMPLETED"


def test_artifact_read_rejects_rebound_invocation(runtime_parts, scope: Scope, signer):
    runtime, _, _ = runtime_parts
    original = _authority(runtime, signer, scope, key="original")
    receipt = _execute(runtime, original)
    assert receipt.result is not None
    digest = receipt.result["artifacts"][-1]["digest"]

    candidate = _authority(
        runtime,
        signer,
        scope,
        key="candidate",
        skill_id="progressive-skill-disclosure",
        inputs={
            "skill_metadata": [],
            "query_terms": [],
            "context_token_budget": 1,
            "candidate_permissions": [],
        },
    )
    forged = Invocation(
        invocation_id=original[0].invocation_id,
        scope=candidate[0].scope,
        skill_id=candidate[0].skill_id,
        action=candidate[0].action,
        idempotency_key=candidate[0].idempotency_key,
        request_digest=candidate[0].request_digest,
        issued_at=candidate[0].issued_at,
        expires_at=candidate[0].expires_at,
    )
    decision = PolicyDecision(
        decision_id="decision-rebound",
        invocation_id=forged.invocation_id,
        scope_digest=scope.digest,
        skill_id=forged.skill_id,
        action=forged.action,
        effect=PolicyEffect.ALLOW,
        policy_revision=digest_object({"policy": "rebound"}, domain="policy"),
        decided_at=forged.issued_at,
        expires_at=forged.expires_at,
    )
    lease = CapabilityLease(
        lease_id="lease-rebound",
        invocation_id=forged.invocation_id,
        scope=scope,
        skill_id=forged.skill_id,
        action=forged.action,
        request_digest=forged.request_digest,
        policy_decision_id=decision.decision_id,
        policy_decision_digest=decision.digest,
        issued_at=forged.issued_at,
        expires_at=forged.expires_at,
    )
    proof = signer.mint_proof("test-key", forged, decision, lease)
    with pytest.raises(AuthorizationError) as denied:
        runtime.read_artifact(
            forged,
            digest=digest,
            decision=decision,
            lease=lease,
            authority_proof=proof,
        )
    assert denied.value.code == "ARTIFACT_READ_BINDING_MISMATCH"


def test_same_idempotency_key_with_different_request_conflicts(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    first = _authority(runtime, signer, scope, inputs=_inputs("local"), key="same-key")
    _execute(runtime, first)
    second = _authority(runtime, signer, scope, inputs=_inputs("changed"), key="same-key")
    with pytest.raises(IdempotencyConflict):
        _execute(runtime, second)
    assert store.verify_scope_integrity(scope.tenant_id, scope.project_id)["status"] == "OK"


def test_crash_resume_from_executing_and_stale_cas_rejected(runtime_parts, scope, signer, verifier):
    runtime, store, _ = runtime_parts
    bundle = _authority(runtime, signer, scope, key="crash")
    invocation, decision, lease, proof, inputs = bundle
    verifier.verify(invocation, decision, lease, proof)
    writer = runtime._writer
    snapshot = writer.begin_invocation(invocation, lease, inputs)
    snapshot = writer.transition_invocation(
        scope,
        invocation.invocation_id,
        expected_sequence=snapshot.sequence,
        expected_state="PENDING",
        new_state="AUTHORIZED",
    )
    with pytest.raises(TransitionConflict):
        writer.transition_invocation(
            scope,
            invocation.invocation_id,
            expected_sequence=0,
            expected_state="PENDING",
            new_state="AUTHORIZED",
        )
    snapshot = writer.transition_invocation(
        scope,
        invocation.invocation_id,
        expected_sequence=snapshot.sequence,
        expected_state="AUTHORIZED",
        new_state="EXECUTING",
    )
    writer.append_checkpoint(
        scope,
        invocation.invocation_id,
        {"phase": "before-handler"},
        event_id="crash-checkpoint",
    )
    resumed = _execute(runtime, bundle)
    assert snapshot.state == "EXECUTING"
    assert resumed.state == "COMPLETED"
    assert store.latest_checkpoint(scope, invocation.invocation_id) is not None


def test_direct_store_mutation_without_runtime_capability_is_rejected(
    runtime_parts,
    scope,
    signer,
):
    runtime, store, _ = runtime_parts
    invocation, _, lease, _, inputs = _authority(runtime, signer, scope, key="direct-store")
    assert not hasattr(store, "begin_invocation")
    assert not hasattr(public_package, "SQLiteControlPlaneStore")
    with pytest.raises(StoreError) as denied:
        store._begin_invocation(
            invocation,
            lease,
            inputs,
            _runtime_capability=object(),
        )
    assert denied.value.code == "STORE_MUTATION_CAPABILITY_REQUIRED"
    assert store.verify_all_integrity()["scope_count"] == 0


def test_append_only_trigger_and_digest_verifier_detect_tamper(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    bundle = _authority(runtime, signer, scope, key="tamper")
    _execute(runtime, bundle)
    with pytest.raises(sqlite3.IntegrityError, match="append-only journal"):
        store._connection.execute(
            "UPDATE journal_entries SET kind='TAMPERED' WHERE tenant_id=? AND project_id=?",
            (scope.tenant_id, scope.project_id),
        )
    store._connection.execute(
        "UPDATE invocations SET result_json='{}' WHERE tenant_id=? AND project_id=?",
        (scope.tenant_id, scope.project_id),
    )
    with pytest.raises(IntegrityError) as tampered:
        store.verify_scope_integrity(scope.tenant_id, scope.project_id)
    assert tampered.value.code == "RESULT_TAMPERED"


def test_replay_and_artifact_read_reject_tampered_result(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    bundle = _authority(runtime, signer, scope, key="tampered-replay")
    receipt = _execute(runtime, bundle)
    assert receipt.result is not None
    artifact_digest = receipt.result["artifacts"][-1]["digest"]
    store._connection.execute(
        "UPDATE invocations SET result_json='{}' WHERE tenant_id=? AND project_id=?",
        (scope.tenant_id, scope.project_id),
    )

    with pytest.raises(IntegrityError) as replay_rejected:
        _execute(runtime, bundle)
    assert replay_rejected.value.code == "RESULT_TAMPERED"
    with pytest.raises(IntegrityError) as artifact_rejected:
        runtime.read_artifact(
            bundle[0],
            digest=artifact_digest,
            decision=bundle[1],
            lease=bundle[2],
            authority_proof=bundle[3],
        )
    assert artifact_rejected.value.code == "RESULT_TAMPERED"


def test_snapshot_rejects_recomputed_result_with_wrong_skill_binding(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    bundle = _authority(runtime, signer, scope, key="tampered-result-binding")
    _execute(runtime, bundle)
    row = store._connection.execute(
        "SELECT result_json FROM invocations WHERE tenant_id=? AND project_id=?",
        (scope.tenant_id, scope.project_id),
    ).fetchone()
    assert row is not None
    result = strict_json_loads(row["result_json"])
    assert isinstance(result, dict)
    result["skill_id"] = "different-skill"
    store._connection.execute(
        "UPDATE invocations SET result_json=?, result_digest=? WHERE tenant_id=? AND project_id=?",
        (
            canonical_json(result),
            digest_object(result, domain="handler-result"),
            scope.tenant_id,
            scope.project_id,
        ),
    )

    with pytest.raises(IntegrityError) as rejected:
        store.get_invocation(scope, bundle[0].invocation_id)
    assert rejected.value.code == "RESULT_TAMPERED"


def test_snapshot_rejects_request_and_state_result_inconsistency(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    request_bundle = _authority(runtime, signer, scope, key="tampered-request")
    _execute(runtime, request_bundle)
    store._connection.execute(
        "UPDATE invocations SET request_json='{}' WHERE tenant_id=? AND project_id=? AND invocation_id=?",
        (scope.tenant_id, scope.project_id, request_bundle[0].invocation_id),
    )
    with pytest.raises(IntegrityError) as request_rejected:
        store.get_invocation(scope, request_bundle[0].invocation_id)
    assert request_rejected.value.code == "REQUEST_TAMPERED"

    state_bundle = _authority(runtime, signer, scope, key="tampered-state")
    _execute(runtime, state_bundle)
    store._connection.execute(
        "UPDATE invocations SET state='FAILED' WHERE tenant_id=? AND project_id=? AND invocation_id=?",
        (scope.tenant_id, scope.project_id, state_bundle[0].invocation_id),
    )
    with pytest.raises(IntegrityError) as state_rejected:
        store.get_invocation(scope, state_bundle[0].invocation_id)
    assert state_rejected.value.code == "RESULT_TAMPERED"


@pytest.mark.parametrize(
    ("column", "value", "expected_code"),
    [
        ("payload_json", '{ "tampered":true}', "JOURNAL_PAYLOAD_TAMPERED"),
        ("payload_digest", _fixed_digest("a"), "JOURNAL_PAYLOAD_TAMPERED"),
        ("entry_digest", _fixed_digest("b"), "JOURNAL_ENTRY_TAMPERED"),
        ("previous_digest", _fixed_digest("c"), "JOURNAL_CHAIN_INVALID"),
    ],
)
def test_latest_checkpoint_validates_each_persisted_field(
    runtime_parts,
    scope,
    signer,
    column,
    value,
    expected_code,
):
    runtime, store, _ = runtime_parts
    bundle = _authority(runtime, signer, scope, key=f"checkpoint-{column}")
    _execute(runtime, bundle)
    store._connection.execute("DROP TRIGGER journal_entries_immutable_update")
    store._connection.execute(
        f"UPDATE journal_entries SET {column}=? WHERE tenant_id=? AND project_id=? AND stream='CHECKPOINT'",
        (value, scope.tenant_id, scope.project_id),
    )
    _restore_journal_trigger(store, "UPDATE")

    with pytest.raises(IntegrityError) as rejected:
        store.latest_checkpoint(scope, bundle[0].invocation_id)
    assert rejected.value.code == expected_code


def test_latest_checkpoint_validates_interleaved_stream_from_genesis(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    first = _authority(runtime, signer, scope, key="checkpoint-first")
    second = _authority(runtime, signer, scope, key="checkpoint-second")
    _execute(runtime, first)
    _execute(runtime, second)
    store._connection.execute("DROP TRIGGER journal_entries_immutable_update")
    store._connection.execute(
        """
        UPDATE journal_entries SET payload_json='{}'
        WHERE tenant_id=? AND project_id=? AND stream='CHECKPOINT' AND sequence=1
        """,
        (scope.tenant_id, scope.project_id),
    )
    _restore_journal_trigger(store, "UPDATE")

    with pytest.raises(IntegrityError) as rejected:
        store.latest_checkpoint(scope, second[0].invocation_id)
    assert rejected.value.code == "JOURNAL_PAYLOAD_TAMPERED"


def test_latest_checkpoint_rejects_chain_gap(runtime_parts, scope, signer):
    runtime, store, _ = runtime_parts
    first = _authority(runtime, signer, scope, key="checkpoint-delete-first")
    second = _authority(runtime, signer, scope, key="checkpoint-delete-second")
    _execute(runtime, first)
    _execute(runtime, second)
    store._connection.execute("DROP TRIGGER journal_entries_immutable_delete")
    store._connection.execute(
        """
        DELETE FROM journal_entries
        WHERE tenant_id=? AND project_id=? AND stream='CHECKPOINT' AND sequence=1
        """,
        (scope.tenant_id, scope.project_id),
    )
    _restore_journal_trigger(store, "DELETE")

    with pytest.raises(IntegrityError) as rejected:
        store.latest_checkpoint(scope, second[0].invocation_id)
    assert rejected.value.code == "JOURNAL_SEQUENCE_INVALID"


def test_latest_checkpoint_enforces_chain_resource_limits(runtime_parts, scope, signer, monkeypatch):
    runtime, store, _ = runtime_parts
    first = _authority(runtime, signer, scope, key="checkpoint-limit-first")
    second = _authority(runtime, signer, scope, key="checkpoint-limit-second")
    _execute(runtime, first)
    _execute(runtime, second)

    monkeypatch.setattr(store_module, "_MAX_CHECKPOINT_CHAIN_ROWS", 1)
    assert store.latest_checkpoint(scope, first[0].invocation_id) is not None
    with pytest.raises(IntegrityError) as row_limit:
        store.latest_checkpoint(scope, second[0].invocation_id)
    assert row_limit.value.code == "JOURNAL_CHAIN_LIMIT"

    monkeypatch.setattr(store_module, "_MAX_CHECKPOINT_CHAIN_ROWS", 10)
    monkeypatch.setattr(store_module, "_MAX_CHECKPOINT_CHAIN_PAYLOAD_BYTES", 1)
    with pytest.raises(IntegrityError) as byte_limit:
        store.latest_checkpoint(scope, first[0].invocation_id)
    assert byte_limit.value.code == "JOURNAL_CHAIN_LIMIT"


def test_store_integrity_verification_enforces_streaming_limits(runtime_parts, scope, signer, monkeypatch):
    runtime, store, _ = runtime_parts
    first = _authority(runtime, signer, scope, key="integrity-limit-first")
    second = _authority(runtime, signer, scope, key="integrity-limit-second")
    _execute(runtime, first)
    _execute(runtime, second)
    other_scope = Scope(
        tenant_id="tenant-other",
        project_id="project-other",
        actor_id=scope.actor_id,
        revision=scope.revision,
    )
    other = _authority(runtime, signer, other_scope, key="integrity-limit-other")
    _execute(runtime, other)

    original_invocations = store_module._MAX_INTEGRITY_INVOCATIONS
    original_journal_entries = store_module._MAX_INTEGRITY_JOURNAL_ENTRIES
    original_json_bytes = store_module._MAX_INTEGRITY_JSON_BYTES
    original_scopes = store_module._MAX_INTEGRITY_SCOPES
    original_discovery_rows = store_module._MAX_INTEGRITY_SCOPE_DISCOVERY_ROWS

    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_INVOCATIONS", 1)
    with pytest.raises(IntegrityError) as invocation_limit:
        store.verify_scope_integrity(scope.tenant_id, scope.project_id)
    assert invocation_limit.value.code == "STORE_INTEGRITY_LIMIT"

    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_INVOCATIONS", original_invocations)
    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_JOURNAL_ENTRIES", 1)
    with pytest.raises(IntegrityError) as journal_limit:
        store.verify_scope_integrity(scope.tenant_id, scope.project_id)
    assert journal_limit.value.code == "STORE_INTEGRITY_LIMIT"

    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_JOURNAL_ENTRIES", original_journal_entries)
    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_JSON_BYTES", 1)
    with pytest.raises(IntegrityError) as byte_limit:
        store.verify_scope_integrity(scope.tenant_id, scope.project_id)
    assert byte_limit.value.code == "STORE_INTEGRITY_LIMIT"

    def stored_json_bytes(candidate_scope: Scope) -> int:
        invocation_bytes = store._connection.execute(
            """
            SELECT COALESCE(SUM(length(CAST(request_json AS BLOB)) +
                                COALESCE(length(CAST(result_json AS BLOB)), 0)), 0)
            FROM invocations WHERE tenant_id=? AND project_id=?
            """,
            (candidate_scope.tenant_id, candidate_scope.project_id),
        ).fetchone()[0]
        journal_bytes = store._connection.execute(
            """
            SELECT COALESCE(SUM(length(CAST(payload_json AS BLOB))), 0)
            FROM journal_entries WHERE tenant_id=? AND project_id=?
            """,
            (candidate_scope.tenant_id, candidate_scope.project_id),
        ).fetchone()[0]
        return int(invocation_bytes) + int(journal_bytes)

    shared_byte_limit = max(stored_json_bytes(scope), stored_json_bytes(other_scope))
    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_JSON_BYTES", shared_byte_limit)
    assert store.verify_scope_integrity(scope.tenant_id, scope.project_id)["status"] == "OK"
    assert store.verify_scope_integrity(other_scope.tenant_id, other_scope.project_id)["status"] == "OK"
    with pytest.raises(IntegrityError) as aggregate_byte_limit:
        store.verify_all_integrity()
    assert aggregate_byte_limit.value.code == "STORE_INTEGRITY_LIMIT"

    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_JSON_BYTES", original_json_bytes)
    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_SCOPES", 1)
    with pytest.raises(IntegrityError) as scope_limit:
        store.verify_all_integrity()
    assert scope_limit.value.code == "STORE_INTEGRITY_LIMIT"

    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_SCOPES", original_scopes)
    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_SCOPE_DISCOVERY_ROWS", 1)
    with pytest.raises(IntegrityError) as discovery_limit:
        store.verify_all_integrity()
    assert discovery_limit.value.code == "STORE_INTEGRITY_LIMIT"

    monkeypatch.setattr(store_module, "_MAX_INTEGRITY_SCOPE_DISCOVERY_ROWS", original_discovery_rows)
    assert store.verify_all_integrity()["scope_count"] == 2

    original_granularity = store_module._SQLITE_PROGRESS_GRANULARITY
    original_vm_steps = store_module._MAX_READ_VM_STEPS
    monkeypatch.setattr(store_module, "_SQLITE_PROGRESS_GRANULARITY", 1)
    monkeypatch.setattr(store_module, "_MAX_READ_VM_STEPS", 1)
    with pytest.raises(IntegrityError) as instruction_limit:
        store.verify_all_integrity()
    assert instruction_limit.value.code == "STORE_INTEGRITY_LIMIT"
    assert store._connection.in_transaction is False
    monkeypatch.setattr(store_module, "_SQLITE_PROGRESS_GRANULARITY", original_granularity)
    monkeypatch.setattr(store_module, "_MAX_READ_VM_STEPS", original_vm_steps)
    assert store.verify_all_integrity()["scope_count"] == 2


def test_e0_gate_fails_closed_for_local_and_caller_verified_evidence(scope: Scope):
    now = utc_now()
    subject = digest_object({"subject": 1}, domain="subject")
    records = (
        Evidence(
            evidence_id="ev-local",
            scope=scope,
            invocation_id="inv-local",
            category="INGESTION",
            subject_digest=subject,
            content_digest=digest_object({"evidence": 1}, domain="evidence"),
            status=EvidenceStatus.LOCAL_EXECUTED_SELF_ATTESTED,
            producer_id="producer-a",
            verifier_id=None,
            authorization_id="decision-1",
            produced_at=now,
        ),
        Evidence(
            evidence_id="ev-fake-verified",
            scope=scope,
            invocation_id="inv-local",
            category="MANIFEST_INTEGRITY",
            subject_digest=subject,
            content_digest=digest_object({"evidence": 2}, domain="evidence"),
            status=EvidenceStatus.VERIFIED,
            producer_id="producer-b",
            verifier_id="caller-verifier",
            authorization_id="decision-1",
            produced_at=now,
        ),
    )
    result = E0E5Gate(clock=lambda: now).evaluate(
        GateLevel.E0,
        scope=scope,
        subject_digest=subject,
        evidence=records,
        authorization_id="decision-1",
    )
    assert result.passed is False
    assert result.status == "BLOCKED"
    assert any("LOCAL_EXECUTED_SELF_ATTESTED" in reason for reason in result.reasons)
    assert "ev-fake-verified:TRUST_VERIFICATION_FAILED" in result.reasons
    assert result.certification_status == "NOT_CERTIFIED"
    assert not hasattr(public_package, "E0E5Gate")


def test_e0_gate_bounds_infinite_evidence_and_obligation_iterables(scope: Scope):
    now = utc_now()
    subject = digest_object({"subject": "bounded"}, domain="subject")
    record = Evidence(
        evidence_id="ev-bounded",
        scope=scope,
        invocation_id="inv-bounded",
        category="INGESTION",
        subject_digest=subject,
        content_digest=digest_object({"evidence": "bounded"}, domain="evidence"),
        status=EvidenceStatus.NOT_RUN,
        producer_id="producer-bounded",
        verifier_id=None,
        authorization_id="decision-bounded",
        produced_at=now,
    )
    obligation = Obligation(
        obligation_id="obligation-bounded",
        kind="TEST",
        description="bounded obligation",
    )
    yielded = {"evidence": 0, "obligations": 0}

    def infinite_evidence():
        while True:
            yielded["evidence"] += 1
            yield record

    def infinite_obligations():
        while True:
            yielded["obligations"] += 1
            yield obligation

    class CountingVerifier:
        calls = 0

        def verify(self, *_args, **_kwargs):
            self.calls += 1

    verifier = CountingVerifier()
    gate = E0E5Gate(
        evidence_verifier=verifier,
        clock=lambda: now,
        max_evidence_records=3,
        max_obligations=2,
    )
    with pytest.raises(ContractError) as evidence_limit:
        gate.evaluate(
            GateLevel.E0,
            scope=scope,
            subject_digest=subject,
            evidence=infinite_evidence(),
            authorization_id="decision-bounded",
        )
    assert evidence_limit.value.code == "GATE_INPUT_LIMIT"
    assert yielded["evidence"] == 4
    assert verifier.calls == 0

    with pytest.raises(ContractError) as obligation_limit:
        gate.evaluate(
            GateLevel.E0,
            scope=scope,
            subject_digest=subject,
            evidence=(),
            obligations=infinite_obligations(),
            authorization_id="decision-bounded",
        )
    assert obligation_limit.value.code == "GATE_INPUT_LIMIT"
    assert yielded["obligations"] == 3
    assert verifier.calls == 0


def test_e0_gate_enforces_aggregate_input_byte_limit(scope: Scope):
    now = utc_now()
    subject = digest_object({"subject": "bytes"}, domain="subject")
    record = Evidence(
        evidence_id="ev-byte-limit",
        scope=scope,
        invocation_id="inv-byte-limit",
        category="INGESTION",
        subject_digest=subject,
        content_digest=digest_object({"evidence": "bytes"}, domain="evidence"),
        status=EvidenceStatus.NOT_RUN,
        producer_id="producer-byte-limit",
        verifier_id=None,
        authorization_id="decision-byte-limit",
        produced_at=now,
        metadata={"bounded_note": "x" * 256},
    )
    obligation = Obligation(
        obligation_id="obligation-byte-limit",
        kind="TEST",
        description="bounded obligation",
    )
    evidence_bytes = len(canonical_json_bytes(record))
    obligation_bytes = len(canonical_json_bytes(obligation))
    shared_limit = max(evidence_bytes, obligation_bytes)
    assert evidence_bytes + obligation_bytes > shared_limit
    gate = E0E5Gate(clock=lambda: now, max_input_bytes=shared_limit)
    with pytest.raises(ContractError) as rejected:
        gate.evaluate(
            GateLevel.E0,
            scope=scope,
            subject_digest=subject,
            evidence=(record,),
            obligations=(obligation,),
            authorization_id="decision-byte-limit",
        )
    assert rejected.value.code == "GATE_INPUT_LIMIT"

    revoked_gate = E0E5Gate(
        clock=lambda: now,
        max_revoked_authorizations=1,
        max_input_bytes=32,
    )
    with pytest.raises(ContractError) as revoked_count:
        revoked_gate.evaluate(
            GateLevel.E0,
            scope=scope,
            subject_digest=subject,
            evidence=(),
            authorization_id="decision-byte-limit",
            revoked_authorization_ids=frozenset({"revoked-a", "revoked-b"}),
        )
    assert revoked_count.value.code == "GATE_INPUT_LIMIT"


def test_cli_gate_never_promotes_caller_json(scope: Scope):
    response = _gate(
        {
            "gate": "E0",
            "scope": scope.to_dict(),
            "subject_digest": digest_object({"subject": "x"}, domain="subject"),
            "evidence": [{"status": "VERIFIED", "verifier_id": "caller"}],
            "obligations": [],
            "authorization_id": "decision-caller",
        }
    )
    assert response["passed"] is False
    assert response["status"] == "NOT_RUN"
    assert response["certification_status"] == "NOT_CERTIFIED"


def test_unknown_skill_alias_and_unknown_input_are_rejected(runtime_parts, scope):
    runtime, _, _ = runtime_parts
    for skill_id in ("unknown-skill", "K1", "universal_agent_skill_runtime"):
        with pytest.raises(ContractError) as unknown:
            runtime.prepare_invocation(
                scope=scope,
                skill_id=skill_id,
                action="plan",
                inputs={},
                idempotency_key=f"unknown-{skill_id}",
            )
        assert unknown.value.code == "UNKNOWN_SKILL"
    with pytest.raises(ContractError) as extra:
        runtime.prepare_invocation(
            scope=scope,
            skill_id=SKILL_ID,
            action="plan",
            inputs={**_inputs(), "unused": "value"},
            idempotency_key="unknown-field",
        )
    assert extra.value.code == "UNKNOWN_INPUT_FIELD"


def test_handler_request_and_registry_are_not_public_execution_surfaces(
    runtime_parts,
    scope,
    signer,
):
    runtime, _, _ = runtime_parts
    invocation, _, lease, _, inputs = _authority(runtime, signer, scope, key="handler-bypass")
    with pytest.raises(AuthorizationError) as denied:
        HandlerRequest(invocation=invocation, lease=lease, inputs=inputs)
    assert denied.value.code == "RUNTIME_EXECUTION_CAPABILITY_REQUIRED"
    kernels = importlib.import_module("elmos_commercial_expansion.kernels")
    assert "EXACT_SKILL_HANDLERS" not in kernels.__all__
    assert not hasattr(public_package, "HandlerRequest")
    assert not hasattr(public_package, "CapabilityLease")


def test_registry_binds_85_distinct_self_identified_handlers_and_contracts():
    handlers, contracts = _exact_registry()
    assert len(handlers) == len(contracts) == 85
    assert len({id(value) for value in handlers.values()}) == 85
    assert all(getattr(handler, "__elmos_exact_skill_id__", None) == skill for skill, handler in handlers.items())
    status = get_commercial_status()
    assert status["exact_registry"] is True
    assert status["handler_source_sha256"]


def test_authority_bound_algorithms_are_partial_deterministic_and_fail_closed(
    runtime_parts,
    scope: Scope,
    signer: LocalHMACAuthoritySigner,
):
    runtime, _, _ = runtime_parts
    for index, case in enumerate(_bounded_algorithm_cases(scope)):
        skill_id = case["skill"]
        inputs = case["inputs"]
        reordered = case["reordered"]
        invalid = case["invalid"]
        assert isinstance(skill_id, str)
        assert isinstance(inputs, dict)
        assert isinstance(reordered, dict)
        assert isinstance(invalid, dict)

        receipt = _execute(
            runtime,
            _authority(
                runtime,
                signer,
                scope,
                key=f"bounded-{index}-primary",
                skill_id=skill_id,
                action="analyze",
                inputs=inputs,
            ),
        )
        replay = _execute(
            runtime,
            _authority(
                runtime,
                signer,
                scope,
                key=f"bounded-{index}-reordered",
                skill_id=skill_id,
                action="analyze",
                inputs=reordered,
            ),
        )
        assert receipt.outcome == replay.outcome == "NOT_RUN"
        assert receipt.result is not None
        assert replay.result is not None
        output = receipt.result["output"]
        reordered_output = replay.result["output"]
        assert output["bounded_subcapability_executed"] is True
        assert output["objective_coverage"] == "PARTIAL"
        assert output["algorithm_result"] == reordered_output["algorithm_result"]
        assert receipt.result["evidence"]
        assert all(
            evidence["status"] == "NOT_RUN"
            for evidence in receipt.result["evidence"]
        )
        value = output["algorithm_result"]
        path = case["path"]
        assert isinstance(path, tuple)
        for component in path:
            value = value[component]
        assert value == case["value"]

        with pytest.raises(ContractError) as rejected:
            _execute(
                runtime,
                _authority(
                    runtime,
                    signer,
                    scope,
                    key=f"bounded-{index}-invalid",
                    skill_id=skill_id,
                    action="analyze",
                    inputs=invalid,
                ),
            )
        assert rejected.value.code == case["code"]


def test_public_kernel_catalog_exposes_only_read_only_input_contract_metadata():
    kernels = list_capability_kernels()
    contracts = {
        skill_id: contract
        for kernel in kernels
        for skill_id, contract in kernel["input_contracts"].items()
    }
    assert len(contracts) == 85
    assert contracts["progressive-skill-disclosure"] == {
        "required": [
            "candidate_permissions",
            "context_token_budget",
            "query_terms",
            "skill_metadata",
        ],
        "optional": [],
        "ephemeral_sensitive_fields": [],
    }
    assert contracts["secret-egress-control"]["ephemeral_sensitive_fields"] == ["text"]
    assert not any(callable(value) for contract in contracts.values() for value in contract.values())


def test_canonical_json_rejects_ambiguity_limits_and_aggregate_mapping():
    with pytest.raises(ContractError) as duplicate:
        strict_json_loads('{"a":1,"a":2}')
    assert duplicate.value.code == "DUPLICATE_JSON_KEY"
    with pytest.raises(ContractError) as number:
        strict_json_loads('{"value":NaN}')
    assert number.value.code == "NON_CANONICAL_NUMBER"
    with pytest.raises(ContractError) as byte_limit:
        strict_json_loads('{"value":"123456"}', limits=JSONLimits(max_bytes=8))
    assert byte_limit.value.code == "JSON_BYTE_LIMIT"
    with pytest.raises(ContractError) as depth:
        strict_json_loads('[[[0]]]', limits=JSONLimits(max_depth=1))
    assert depth.value.code == "JSON_DEPTH_LIMIT"
    with pytest.raises(ContractError) as nodes:
        strict_json_loads('[1,2,3]', limits=JSONLimits(max_nodes=3))
    assert nodes.value.code == "JSON_NODE_LIMIT"
    aggregate = {f"field-{index}": "x" * 220 for index in range(5_000)}
    with pytest.raises(ContractError) as aggregate_limit:
        to_jsonable(aggregate)
    assert aggregate_limit.value.code == "JSON_BYTE_LIMIT"
    with pytest.raises(ContractError) as member_limit:
        to_jsonable({f"k-{index}": 0 for index in range(10_001)})
    assert member_limit.value.code == "JSON_MEMBER_LIMIT"

    class LengthLyingMapping(Mapping[str, object]):
        def __getitem__(self, key: str) -> object:
            return key

        def __iter__(self) -> Iterator[str]:
            return iter(("a", "b", "c", "d"))

        def __len__(self) -> int:
            return 1

    with pytest.raises(ContractError) as lying_limit:
        to_jsonable(LengthLyingMapping(), limits=JSONLimits(max_members=3))
    assert lying_limit.value.code == "JSON_MEMBER_LIMIT"


@pytest.mark.parametrize(
    "value",
    [
        {"password": "not-allowed"},
        {"value": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
        {"api_key": "sk-abcdefghijklmnopqrstuvwxyz123456"},
    ],
)
def test_raw_secret_shapes_are_rejected(value):
    with pytest.raises(ContractError) as denied:
        validate_handler_inputs(value)
    assert denied.value.code == "RAW_SECRET_INPUT_FORBIDDEN"
    assert validate_handler_inputs({"token_budget": 100, "tokens_consumed": 5})


def test_secret_reference_requires_lease_and_is_never_persisted(runtime_parts, scope, signer, tmp_path):
    runtime, _, _ = runtime_parts
    sentinel = "customer-secret-reference-SENTINEL"
    inputs = {
        "requested_skills": ["repository-semantic-code-graph"],
        "policy": {"credential": {"$secret_ref": sentinel}},
    }
    denied_bundle = _authority(runtime, signer, scope, inputs=inputs, key="secret-ref-denied")
    with pytest.raises(AuthorizationError) as denied:
        _execute(runtime, denied_bundle)
    assert denied.value.code == "SECRET_REFERENCE_NOT_AUTHORIZED"
    allowed_bundle = _authority(
        runtime,
        signer,
        scope,
        inputs=inputs,
        key="secret-ref-allowed",
        secret_refs=frozenset({sentinel}),
    )
    receipt = _execute(runtime, allowed_bundle)
    assert sentinel not in json.dumps(receipt.to_dict())
    assert sentinel.encode() not in _all_files(tmp_path)


def test_ephemeral_secret_scan_and_raw_sql_rows_evidence_do_not_leak(
    runtime_parts,
    scope,
    signer,
    tmp_path,
):
    runtime, _, _ = runtime_parts
    secret = "api_key=SENTINEL_SECRET_12345678901234567890"
    scan = _authority(
        runtime,
        signer,
        scope,
        key="secret-scan",
        skill_id="secret-egress-control",
        action="scan",
        inputs={"text": secret},
    )
    scan_receipt = _execute(runtime, scan)
    assert scan_receipt.outcome == "NOT_RUN"
    assert scan_receipt.result is not None
    assert scan_receipt.result["output"]["bounded_subcapability_executed"] is True
    assert scan_receipt.result["output"]["objective_coverage"] == "PARTIAL"
    assert secret not in json.dumps(scan_receipt.to_dict())

    sql_sentinel = "SENTINEL_SQL_CUSTOMER_ALICE"
    sql_bundle = _authority(
        runtime,
        signer,
        scope,
        key="sql",
        skill_id="sql-dialect-transpiler",
        action="transpile",
        inputs={
            "sql": f"SELECT * FROM customer WHERE name='{sql_sentinel}'",
            "source_engine": "postgresql-16",
            "target_engine": "mysql-8",
        },
    )
    sql_receipt = _execute(runtime, sql_bundle)
    assert sql_receipt.outcome == "EXTERNAL_ADAPTER_REQUIRED"
    assert sql_sentinel not in json.dumps(sql_receipt.to_dict())

    pii_sentinel = "SENTINEL_ROW_PII_ALICE"
    rows_bundle = _authority(
        runtime,
        signer,
        scope,
        key="rows",
        skill_id="data-migration-reconciliation",
        action="reconcile",
        inputs={
            "source_rows": [{"id": 1, "name": pii_sentinel}],
            "target_rows": [{"id": 1, "name": pii_sentinel}],
            "key_fields": ["id"],
        },
    )
    rows_receipt = _execute(runtime, rows_bundle)
    assert rows_receipt.outcome == "NOT_RUN"
    assert rows_receipt.result is not None
    assert rows_receipt.result["output"]["bounded_subcapability_executed"] is True
    assert rows_receipt.result["output"]["objective_coverage"] == "PARTIAL"
    assert pii_sentinel not in json.dumps(rows_receipt.to_dict())

    evidence_sentinel = "SENTINEL_RAW_EVIDENCE_ALICE"
    raw = {"customer": evidence_sentinel, "passed": True}
    evidence_bundle = _authority(
        runtime,
        signer,
        scope,
        key="evidence",
        skill_id="compiler-grade-certification-gate",
        action="evaluate",
        inputs={
            "evidence": [
                {
                    "category": "COMPILER_GATE",
                    "raw": raw,
                    "content_digest": digest_object(raw, domain="commercial-evidence-raw"),
                    "status": "VERIFIED",
                    "producer_id": "caller-producer",
                }
            ]
        },
    )
    evidence_receipt = _execute(runtime, evidence_bundle)
    assert evidence_receipt.outcome == "NOT_RUN"
    assert evidence_receipt.result is not None
    assert evidence_receipt.result["output"]["decision"] == "EVIDENCE_PENDING"
    assert evidence_receipt.result["output"]["independently_verified_count"] == 0
    serialized = json.dumps(evidence_receipt.to_dict())
    assert evidence_sentinel not in serialized

    persisted = _all_files(tmp_path)
    for sentinel in (secret, sql_sentinel, pii_sentinel, evidence_sentinel):
        assert sentinel.encode() not in persisted


def test_k4_execution_contract_minimizes_input_paths_and_names(
    runtime_parts,
    scope: Scope,
    signer: LocalHMACAuthoritySigner,
    tmp_path: Path,
):
    runtime, _, _ = runtime_parts
    path_sentinel = "SENTINEL_PRIVATE_REPOSITORY_PATH"
    bundle = _authority(
        runtime,
        signer,
        scope,
        key="k4-minimized-bindings",
        skill_id="hermetic-build-environment",
        action="plan",
        inputs={
            "command": ["build-tool", "--offline"],
            "input_digests": {
                f"/customer/repository/{path_sentinel}/source": _fixed_digest("f"),
            },
            "quotas": {"cpu_seconds": 10},
        },
    )
    receipt = _execute(runtime, bundle)
    assert receipt.outcome == "EXTERNAL_ADAPTER_REQUIRED"
    assert receipt.result is not None
    contract = receipt.result["output"]["execution_contract"]
    assert contract["input_binding_count"] == 1
    assert contract["input_binding_digest"].startswith("sha256:")
    assert "input_digests" not in contract
    assert "required_sandbox_policy" in contract
    assert "sandbox" not in contract
    assert path_sentinel not in json.dumps(receipt.to_dict())
    assert path_sentinel.encode() not in _all_files(tmp_path)


@pytest.mark.parametrize(
    ("skill_id", "inputs", "expected"),
    [
        (
            "policy-as-code-kernel",
            {"policy": {"allow": ["deploy"]}, "requested_action": "deploy", "resource": "prod"},
            "DENY",
        ),
        (
            "multi-tenant-isolation-certifier",
            {"isolation_contract": {}, "evidence": [{"status": "VERIFIED"}]},
            "UNTRUSTED_CANDIDATE_ONLY",
        ),
        (
            "transaction-semantic-equivalence",
            {"source_contract": {}, "target_contract": {}, "evidence": [{"status": "VERIFIED"}]},
            "UNTRUSTED_CANDIDATE_ONLY",
        ),
        (
            "skill-promotion-canary",
            {"candidate_version": "v2", "canary_policy": {}, "external_evidence": [{"status": "VERIFIED"}]},
            "UNVERIFIED_CANDIDATE_ONLY",
        ),
    ],
)
def test_caller_policy_and_evidence_never_unlock_trusted_outcomes(
    runtime_parts,
    scope,
    signer,
    skill_id,
    inputs,
    expected,
):
    runtime, _, _ = runtime_parts
    bundle = _authority(
        runtime,
        signer,
        scope,
        key=f"candidate-{skill_id}",
        skill_id=skill_id,
        action="evaluate",
        inputs=inputs,
    )
    receipt = _execute(runtime, bundle)
    assert receipt.outcome == "NOT_RUN"
    assert receipt.result is not None
    output = receipt.result["output"]
    assert expected in json.dumps(output)
    assert output.get("decision", "DENY") != "ALLOW"


def test_sqlite_and_artifact_paths_reject_symlink_hardlink_and_protected_root(
    tmp_path: Path,
    monkeypatch,
):
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(StoreError) as symlink_parent:
        SQLiteControlPlaneStore(alias / "db.sqlite3")
    assert symlink_parent.value.code == "SQLITE_PATH_UNSAFE"
    with pytest.raises(ContractError) as artifact_parent:
        ContentAddressedArtifactStore(alias / "artifacts")
    assert artifact_parent.value.code == "ARTIFACT_PATH_INVALID"

    database = tmp_path / "hardlink" / "db.sqlite3"
    store = SQLiteControlPlaneStore(database)
    store.close()
    linked = database.with_name("linked.sqlite3")
    os.link(database, linked)
    with pytest.raises(StoreError) as hardlink:
        SQLiteControlPlaneStore.open_readonly(database)
    assert hardlink.value.code == "SQLITE_PATH_UNSAFE"

    protected = tmp_path / "protected"
    protected.mkdir(mode=0o700)
    monkeypatch.chdir(protected)
    with pytest.raises(ContractError) as cwd_root:
        ContentAddressedArtifactStore(protected)
    assert cwd_root.value.code == "ARTIFACT_PATH_INVALID"


def test_sqlite_detects_path_swap_during_connect(tmp_path: Path, monkeypatch):
    import elmos_commercial_expansion.store as store_module

    database = tmp_path / "swap" / "db.sqlite3"
    initial = SQLiteControlPlaneStore(database)
    initial.close()
    real_connect = store_module.sqlite3.connect

    def raced_connect(path, *args, **kwargs):
        candidate = Path(path)
        moved = candidate.with_name("moved.sqlite3")
        os.rename(candidate, moved)
        descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(descriptor)
        return real_connect(path, *args, **kwargs)

    monkeypatch.setattr(store_module.sqlite3, "connect", raced_connect)
    with pytest.raises(StoreError) as swapped:
        SQLiteControlPlaneStore(database)
    assert swapped.value.code == "SQLITE_OPEN_UNSAFE"


def test_check_store_is_read_only_redacted_and_rejects_unsafe_paths(tmp_path: Path):
    database = tmp_path / "inspection" / "db.sqlite3"
    store = SQLiteControlPlaneStore(database)
    store.close()
    before = database.read_bytes()
    before_stat = database.stat()
    report = _check_store({"database_path": str(database)})
    after_stat = database.stat()
    assert database.read_bytes() == before
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
    assert "tenant_id" not in json.dumps(report)
    assert "project_id" not in json.dumps(report)
    with ReadonlyControlPlaneStore(database) as readonly:
        assert readonly.verify_all_integrity()["status"] == "OK"

    symlink = database.with_name("alias.sqlite3")
    symlink.symlink_to(database)
    with pytest.raises(StoreError):
        _check_store({"database_path": str(symlink)})
    hardlink = database.with_name("hard.sqlite3")
    os.link(database, hardlink)
    with pytest.raises(StoreError):
        _check_store({"database_path": str(database)})


def test_readonly_store_rejects_same_named_tables_and_fake_integrity_indexes(tmp_path: Path):
    database = tmp_path / "fake-schema" / "db.sqlite3"
    database.parent.mkdir(parents=True)
    database.parent.chmod(0o700)
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_migrations(version INTEGER, applied_at TEXT);
        INSERT INTO schema_migrations VALUES (1, '2026-08-30T00:00:00Z');
        CREATE TABLE invocations(tenant_id TEXT, project_id TEXT, invocation_id TEXT);
        CREATE INDEX idx_invocations_integrity_scan
          ON invocations(tenant_id, project_id, invocation_id);
        CREATE TABLE journal_entries(
          tenant_id TEXT, project_id TEXT, stream TEXT, sequence INTEGER
        );
        CREATE INDEX idx_journal_integrity_scan
          ON journal_entries(tenant_id, project_id, stream, sequence);
        CREATE TRIGGER journal_entries_immutable_update
        BEFORE UPDATE ON journal_entries BEGIN
          SELECT RAISE(ABORT, 'append-only journal');
        END;
        CREATE TRIGGER journal_entries_immutable_delete
        BEFORE DELETE ON journal_entries BEGIN
          SELECT RAISE(ABORT, 'append-only journal');
        END;
        """
    )
    connection.close()
    database.chmod(0o600)

    with pytest.raises(StoreError) as rejected:
        SQLiteControlPlaneStore.open_readonly(database)
    assert rejected.value.code == "STORE_SCHEMA_INVALID"


def test_store_integrity_rejects_schema_version_and_trigger_drift(tmp_path: Path):
    store = SQLiteControlPlaneStore(tmp_path / "schema-drift" / "db.sqlite3")
    store._connection.execute(
        "INSERT INTO schema_migrations(version, applied_at) VALUES (2, ?)",
        (utc_now().isoformat(),),
    )
    with pytest.raises(StoreError) as version_rejected:
        store.verify_all_integrity()
    assert version_rejected.value.code == "STORE_SCHEMA_INVALID"
    assert store._connection.in_transaction is False

    store._connection.execute("DELETE FROM schema_migrations WHERE version=2")
    store._connection.execute("DROP TRIGGER journal_entries_immutable_update")
    with pytest.raises(StoreError) as trigger_rejected:
        store.verify_all_integrity()
    assert trigger_rejected.value.code == "STORE_SCHEMA_INVALID"
    assert store._connection.in_transaction is False
    store.close()


def test_artifact_corrupt_final_is_quarantined_and_retried(runtime_parts, scope: Scope):
    runtime, _, artifact_store = runtime_parts
    payload = b"durable-artifact-payload"
    artifact = runtime._artifact_access.put(
        scope,
        payload,
        media_type="application/octet-stream",
        kind="test",
        producer_id="test-runtime",
    )
    target = next(
        path
        for path in artifact_store.root.rglob(artifact.digest.removeprefix("sha256:"))
        if path.is_file()
    )
    target.write_bytes(b"partial")
    os.chmod(target, 0o600)
    retried = runtime._artifact_access.put(
        scope,
        payload,
        media_type="application/octet-stream",
        kind="test",
        producer_id="test-runtime",
    )
    assert retried.digest == artifact.digest
    assert runtime._artifact_access.get(scope, artifact.digest) == payload
    assert list(target.parent.glob(f".corrupt-{target.name}-*"))


def test_artifact_hardlink_is_rejected(runtime_parts, scope: Scope):
    runtime, _, artifact_store = runtime_parts
    artifact = runtime._artifact_access.put(
        scope,
        b"hardlink-test",
        media_type="application/octet-stream",
        kind="test",
        producer_id="test-runtime",
    )
    target = next(
        path
        for path in artifact_store.root.rglob(artifact.digest.removeprefix("sha256:"))
        if path.is_file()
    )
    os.link(target, target.with_name("unexpected-hardlink"))
    with pytest.raises(IntegrityError) as rejected:
        runtime._artifact_access.get(scope, artifact.digest)
    assert rejected.value.code == "ARTIFACT_PATH_INVALID"


@pytest.mark.parametrize(
    "module_name",
    [
        "k1_skill_runtime",
        "k2_repository_intelligence",
        "k3_transformation",
        "k4_build_execution",
        "k5_verification",
        "k6_security_governance",
        "k7_database_data",
        "k8_observability_evolution",
    ],
)
def test_legacy_kernel_modules_are_absent(module_name: str):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"elmos_commercial_expansion.kernels.{module_name}")


def test_status_is_registry_derived_and_legacy_workflow_is_fail_closed():
    status = get_commercial_status()
    assert status["status"] == "LOCAL_BOUNDED_UNQUALIFIED"
    assert status["status"] != "ACTIVE"
    assert status["skills_count"] == 85
    assert status["external_provider_status"] == "NOT_RUN"
    assert status["projection"] == {
        "status": "PINNED_VERIFIED",
        "valid": True,
        "catalog_sha256": "25b8912a9dcf425982af962ac08cb3203660c7ad5e66887f8a9054a9cfa83178",
        "wrapper_tree_sha256": "062c3abac46b5364dd08f962524d60ef2ef1ef430199d4a66748bf534c761ae1",
        "wrapper_count": 86,
    }
    assert status["qualification"] == {"status": "NOT_RUN", "valid": False, "receipt": None}
    kernels = list_capability_kernels()
    assert len(kernels) == 8
    assert sum(item["exact_handler_count"] for item in kernels) == 85
    assert all(item["status"] == "LOCAL_BOUNDED_UNQUALIFIED" for item in kernels)
    legacy = CommercialCapabilityExpansionService().run_commercial_workflow()
    assert legacy == {
        "status": "NOT_RUN",
        "outcome": "BLOCKED",
        "reason": "SIGNED_EXACT_INVOCATION_REQUIRED",
        "external_provider_status": "NOT_RUN",
        "native_runtime_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }


def test_explicit_repository_root_drives_runtime_and_status_reads(
    tmp_path: Path,
    verifier: HMACAuthorityVerifier,
):
    repository = _repository_root_for_tests()
    status = get_commercial_status(repository)
    kernels = list_capability_kernels(repository)
    store = SQLiteControlPlaneStore(tmp_path / "explicit-root" / "runtime.sqlite3")
    runtime = CommercialCapabilityRuntime(
        store=store,
        artifact_store=ContentAddressedArtifactStore(tmp_path / "explicit-root-artifacts"),
        authority_verifier=verifier,
        repository_root=repository,
    )
    try:
        assert status["status"] == "LOCAL_BOUNDED_UNQUALIFIED"
        assert status["projection"]["status"] == "PINNED_VERIFIED"
        assert len(kernels) == 8
        assert runtime._registry_digest == status["registry_digest"]
        assert runtime._manifest_digest == status["manifest_digest"]
    finally:
        store.close()


@pytest.mark.parametrize(
    "repository_root",
    [Path("."), Path("/")],
    ids=["relative", "filesystem-root"],
)
def test_untrusted_repository_roots_fail_closed(
    repository_root: Path,
    tmp_path: Path,
    verifier: HMACAuthorityVerifier,
):
    with pytest.raises(ContractError) as status_error:
        get_commercial_status(repository_root)
    assert status_error.value.code == "REPOSITORY_ROOT_INVALID"
    with pytest.raises(ContractError) as catalog_error:
        list_capability_kernels(repository_root)
    assert catalog_error.value.code == "REPOSITORY_ROOT_INVALID"

    store = SQLiteControlPlaneStore(
        tmp_path / f"invalid-root-{repository_root == Path('/')}" / "runtime.sqlite3"
    )
    try:
        with pytest.raises(ContractError) as runtime_error:
            CommercialCapabilityRuntime(
                store=store,
                artifact_store=ContentAddressedArtifactStore(
                    tmp_path / f"invalid-root-artifacts-{repository_root == Path('/')}"
                ),
                authority_verifier=verifier,
                repository_root=repository_root,
            )
        assert runtime_error.value.code == "REPOSITORY_ROOT_INVALID"
    finally:
        store.close()


def test_symlink_repository_root_fails_closed(tmp_path: Path):
    repository_link = tmp_path / "repository-link"
    repository_link.symlink_to(_repository_root_for_tests(), target_is_directory=True)
    with pytest.raises(ContractError) as rejected:
        get_commercial_status(repository_link)
    assert rejected.value.code == "REPOSITORY_ROOT_INVALID"


def test_explicit_empty_repository_root_never_falls_back_to_source_checkout(
    tmp_path: Path,
    verifier: HMACAuthorityVerifier,
):
    repository = tmp_path / "empty-repository"
    repository.mkdir(mode=0o700)
    status = get_commercial_status(repository)
    assert status["status"] == "NOT_READY"
    assert status["exact_registry"] is False
    assert status["archive"]["present"] is False
    assert status["projection"] == {"status": "MISSING_OR_INVALID", "valid": False}

    store = SQLiteControlPlaneStore(tmp_path / "empty-root" / "runtime.sqlite3")
    try:
        with pytest.raises(IntegrityError) as rejected:
            CommercialCapabilityRuntime(
                store=store,
                artifact_store=ContentAddressedArtifactStore(tmp_path / "empty-root-artifacts"),
                authority_verifier=verifier,
                repository_root=repository,
            )
        assert rejected.value.code == "REGISTRY_INVALID"
    finally:
        store.close()


def test_projection_receipt_tamper_fails_closed(tmp_path: Path):
    registry_ids = _copy_projection(tmp_path)
    receipt_path = tmp_path / _RECEIPT_RELATIVE
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["installed_wrappers"]["tree_sha256"] = "0" * 64
    _rewrite_json(receipt_path, receipt)

    assert _projection_status(registry_ids, root=tmp_path) == {
        "status": "MISSING_OR_INVALID",
        "valid": False,
    }


def test_catalog_and_matching_receipt_cannot_self_authenticate(tmp_path: Path):
    registry_ids = _copy_projection(tmp_path)
    catalog_path = tmp_path / _CATALOG_RELATIVE
    receipt_path = tmp_path / _RECEIPT_RELATIVE
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["untrusted_self_attestation"] = "forged"
    _rewrite_json(catalog_path, catalog)
    catalog_bytes = catalog_path.read_bytes()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["compiled_catalog"]["sha256"] = hashlib.sha256(catalog_bytes).hexdigest()
    receipt["compiled_catalog"]["tree_sha256"] = _projection_tree_digest(
        {_CATALOG_RELATIVE.name: catalog_bytes}
    )
    _rewrite_json(receipt_path, receipt)

    assert _projection_status(registry_ids, root=tmp_path) == {
        "status": "MISSING_OR_INVALID",
        "valid": False,
    }


def test_dual_root_projection_and_matching_receipt_cannot_self_authenticate(tmp_path: Path):
    registry_ids = _copy_projection(tmp_path)
    for root in (_WORKSPACE_SKILLS_RELATIVE, _RUNTIME_SKILLS_RELATIVE):
        skill_path = tmp_path / root / _MASTER_SKILL_ID / "SKILL.md"
        skill_path.write_bytes(skill_path.read_bytes() + b"\n<!-- forged projection -->\n")
    receipt_path = tmp_path / _RECEIPT_RELATIVE
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["installed_wrappers"]["tree_sha256"] = _projection_tree_digest(
        _wrapper_payloads(tmp_path, registry_ids)
    )
    _rewrite_json(receipt_path, receipt)

    assert _projection_status(registry_ids, root=tmp_path) == {
        "status": "MISSING_OR_INVALID",
        "valid": False,
    }
