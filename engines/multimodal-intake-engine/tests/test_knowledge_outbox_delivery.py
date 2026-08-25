from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from elmos_multimodal_intake._migrations import migrate_connection
from elmos_multimodal_intake.canonical import canonical_digest, canonical_json, sha256_bytes
from elmos_multimodal_intake.errors import (
    AuthorizationError,
    ConflictError,
    IntegrityError,
    NotFoundError,
)
from elmos_multimodal_intake.knowledge_worker import KnowledgeWorker
from elmos_multimodal_intake.models import TenantContext
from elmos_multimodal_intake.persistent_knowledge import PersistentKnowledgeStore
from elmos_multimodal_intake.store import IntakeStore


def _open_scope(
    tmp_path: Path,
    *,
    name: str = "knowledge-outbox.sqlite3",
) -> tuple[IntakeStore, PersistentKnowledgeStore, TenantContext, object]:
    capability = object()
    store = IntakeStore(tmp_path / name)
    context = TenantContext("tenant-outbox", "project-outbox", "actor-outbox")
    store.bootstrap_project(context)
    knowledge = PersistentKnowledgeStore(store, worker_capability=capability)
    return store, knowledge, context, capability


def _create_event(
    store: IntakeStore,
    knowledge: PersistentKnowledgeStore,
    context: TenantContext,
    suffix: str,
) -> str:
    rebuild_id = f"rebuild-{suffix}"
    with store.transaction() as connection:
        return knowledge._event(
            connection,
            context,
            event_type="KNOWLEDGE_REBUILD_JOB_COMPLETED",
            aggregate_id=rebuild_id,
            idempotency_key=f"outbox-event-{suffix}",
            payload={
                "rebuild_id": rebuild_id,
                "target": "content-index",
                "rebuilt_digest": canonical_digest({"suffix": suffix}),
            },
        )


class _ControlledTransport:
    def __init__(self, mode: str = "success") -> None:
        self.mode = mode
        self.calls: list[dict[str, Any]] = []
        self.effects: list[str] = []
        self._lock = threading.Lock()

    def deliver(
        self,
        event: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any]:
        with self._lock:
            self.calls.append(
                {"event": dict(event), "idempotency_key": idempotency_key}
            )
            self.effects.append(str(event["event_id"]))
            mode = self.mode
        if mode == "response-loss":
            raise TimeoutError("provider response was lost after accepting the effect")
        if mode == "invalid-receipt":
            return {
                "event_id": event["event_id"],
                "payload_digest": "0" * 64,
                "delivery_state": "DELIVERED",
                "provider_message_id": f"provider-{event['event_id']}",
            }
        return {
            "event_id": event["event_id"],
            "payload_digest": event["payload_digest"],
            "delivery_state": "DELIVERED",
            "provider_message_id": f"provider-{event['event_id']}",
        }


def _worker(
    knowledge: PersistentKnowledgeStore,
    context: TenantContext,
    capability: object,
    transport: _ControlledTransport,
    executor_id: str,
) -> KnowledgeWorker:
    return KnowledgeWorker(
        knowledge,
        context=context,
        branch="main",
        package_version="package-v1",
        worker_capability=capability,
        transport=transport,
        executor_id=executor_id,
        max_rebuild_targets=1,
        max_outbox_events=1,
        delivery_lease_seconds=30,
    )


def _execution_receipt(
    binding: Mapping[str, Any],
    *,
    executor_id: str,
) -> dict[str, Any]:
    body = {
        "schema_version": "1.0.0",
        **dict(binding),
        "executor_id": executor_id,
        "completed_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    return {**body, "receipt_digest": canonical_digest(body)}


def _reconciliation_receipt(
    state: Mapping[str, Any],
    *,
    delivery_state: str,
    reconciliation_id: str,
) -> dict[str, Any]:
    return {
        "tenant_id": state["tenant_id"],
        "project_id": state["project_id"],
        "actor_id": state["actor_id"],
        "event_id": state["event_id"],
        "event_type": state["event_type"],
        "aggregate_id": state["aggregate_id"],
        "payload_digest": state["payload_digest"],
        "delivery_state": delivery_state,
        "provider_message_id": (
            f"reconciled-{state['event_id']}"
            if delivery_state == "DELIVERED"
            else None
        ),
        "reconciliation_id": reconciliation_id,
    }


def test_v8_migration_backfills_immutable_delivery_binding_and_dual_roots_match(
    tmp_path: Path,
) -> None:
    database = tmp_path / "migration.sqlite3"
    connection = sqlite3.connect(database, isolation_level=None)
    assert migrate_connection(connection, target_version=7) == 7
    payload_json = canonical_json({"rebuild_id": "rebuild-migrated"})
    payload_digest = canonical_digest({"rebuild_id": "rebuild-migrated"})
    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    connection.execute(
        "INSERT INTO knowledge_outbox_events VALUES (?,?,?,?,?,?,?,?,?,?,NULL)",
        (
            "tenant-migrated",
            "project-migrated",
            "actor-migrated",
            "kevt-migrated",
            "KNOWLEDGE_REBUILD_JOB_COMPLETED",
            "rebuild-migrated",
            payload_json,
            payload_digest,
            "migrated-event",
            now,
        ),
    )
    assert migrate_connection(connection, target_version=8) == 8
    row = connection.execute(
        "SELECT * FROM knowledge_outbox_delivery_states WHERE event_id='kevt-migrated'"
    ).fetchone()
    assert row is not None
    assert row[3:9] == (
        "kevt-migrated",
        "KNOWLEDGE_REBUILD_JOB_COMPLETED",
        "rebuild-migrated",
        payload_digest,
        "PENDING",
        0,
    )
    assert migrate_connection(connection, target_version=13) == 13
    connection.close()

    root = Path(__file__).resolve().parents[1]
    assert (
        root / "migrations" / "008_knowledge_outbox_delivery_state.sql"
    ).read_bytes() == (
        root
        / "src"
        / "elmos_multimodal_intake"
        / "migrations"
        / "008_knowledge_outbox_delivery_state.sql"
    ).read_bytes()


def test_two_concurrent_workers_claim_and_publish_one_effect_once(tmp_path: Path) -> None:
    store, knowledge, context, capability = _open_scope(tmp_path)
    event_id = _create_event(store, knowledge, context, "concurrent")
    second_store = IntakeStore(store.database)
    second_knowledge = PersistentKnowledgeStore(
        second_store,
        worker_capability=capability,
    )
    transport = _ControlledTransport()
    workers = (
        _worker(knowledge, context, capability, transport, "worker-a"),
        _worker(second_knowledge, context, capability, transport, "worker-b"),
    )
    start = threading.Barrier(2)

    def execute(worker: KnowledgeWorker) -> dict[str, Any]:
        start.wait(timeout=5)
        return worker.run_once()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(execute, workers))

    assert sorted(result["state"] for result in results) == ["IDLE", "SUCCEEDED"]
    assert [effect for effect in transport.effects if effect == event_id] == [event_id]
    assert len(transport.calls) == 1
    state = knowledge.outbox_delivery_state(context, event_id)
    assert state["delivery_phase"] == "PUBLISHED"
    assert state["delivery_attempt"] == 1
    second_store.close()
    store.close()


@pytest.mark.parametrize(
    ("mode", "error_code"),
    [
        ("response-loss", "KNOWLEDGE_OUTBOX_TRANSPORT_OUTCOME_UNKNOWN"),
        ("invalid-receipt", "KNOWLEDGE_OUTBOX_TRANSPORT_EVIDENCE_INVALID"),
    ],
)
def test_ambiguous_or_invalid_transport_outcome_is_unknown_and_never_auto_replayed(
    tmp_path: Path,
    mode: str,
    error_code: str,
) -> None:
    store, knowledge, context, capability = _open_scope(
        tmp_path,
        name=f"{mode}.sqlite3",
    )
    event_id = _create_event(store, knowledge, context, mode)
    transport = _ControlledTransport(mode)
    worker = _worker(knowledge, context, capability, transport, "worker-unknown")

    with pytest.raises(IntegrityError, match=error_code) as raised:
        worker.run_once()
    assert raised.value.retryable is False
    state = knowledge.outbox_delivery_state(context, event_id)
    assert state["delivery_phase"] == "UNKNOWN"
    assert state["last_error_code"] == error_code
    assert worker.run_once()["state"] == "IDLE"
    assert transport.effects == [event_id]
    store.close()


def test_claimed_lease_can_be_taken_over_but_dispatching_expiry_becomes_unknown(
    tmp_path: Path,
) -> None:
    store, knowledge, context, capability = _open_scope(tmp_path)
    event_id = _create_event(store, knowledge, context, "lease")
    first = knowledge.claim_next_outbox_event(
        context,
        worker_capability=capability,
        claim_token="claim-token-first",
        executor_id="worker-first",
        lease_seconds=30,
    )
    assert first is not None and first["delivery_attempt"] == 1
    expired = (datetime.now(UTC) - timedelta(seconds=1)).replace(
        microsecond=0
    ).isoformat()
    with store.transaction() as connection:
        connection.execute(
            "UPDATE knowledge_outbox_delivery_states SET lease_expires_at=? WHERE event_id=?",
            (expired, event_id),
        )
    second = knowledge.claim_next_outbox_event(
        context,
        worker_capability=capability,
        claim_token="claim-token-second",
        executor_id="worker-second",
        lease_seconds=30,
    )
    assert second is not None and second["event_id"] == event_id
    assert second["delivery_attempt"] == 2
    with pytest.raises(AuthorizationError, match="KNOWLEDGE_OUTBOX_CLAIM_FENCE_MISMATCH"):
        knowledge.mark_outbox_dispatching(
            context,
            event_id,
            worker_capability=capability,
            claim_token="claim-token-first",
        )
    knowledge.mark_outbox_dispatching(
        context,
        event_id,
        worker_capability=capability,
        claim_token="claim-token-second",
    )
    with store.transaction() as connection:
        connection.execute(
            "UPDATE knowledge_outbox_delivery_states SET lease_expires_at=? WHERE event_id=?",
            (expired, event_id),
        )
    assert knowledge.claim_next_outbox_event(
        context,
        worker_capability=capability,
        claim_token="claim-token-third",
        executor_id="worker-third",
    ) is None
    state = knowledge.outbox_delivery_state(context, event_id)
    assert state["delivery_phase"] == "UNKNOWN"
    assert state["delivery_attempt"] == 2
    assert state["last_error_code"] == "KNOWLEDGE_OUTBOX_DISPATCH_OUTCOME_UNKNOWN"
    assert state["last_executor_id"] == "worker-second"
    audit_row = store._connection.execute(
        """
        SELECT last_claim_token_digest,last_executor_id
          FROM knowledge_outbox_delivery_states WHERE event_id=?
        """,
        (event_id,),
    ).fetchone()
    assert audit_row["last_claim_token_digest"] == sha256_bytes(
        b"claim-token-second"
    )
    assert audit_row["last_executor_id"] == "worker-second"
    store.close()


def test_attempt_limit_blocks_delivery_and_terminal_publication_cannot_regress(
    tmp_path: Path,
) -> None:
    store, knowledge, context, capability = _open_scope(tmp_path)
    blocked_event = _create_event(store, knowledge, context, "attempt-limit")
    with store.transaction() as connection:
        connection.execute(
            "UPDATE knowledge_outbox_delivery_states SET attempt=10 WHERE event_id=?",
            (blocked_event,),
        )
    assert knowledge.claim_next_outbox_event(
        context,
        worker_capability=capability,
        claim_token="claim-token-blocked",
        executor_id="worker-blocked",
    ) is None
    assert knowledge.outbox_delivery_state(context, blocked_event)[
        "delivery_phase"
    ] == "BLOCKED"

    published_event = _create_event(store, knowledge, context, "terminal")
    claim_token = "claim-token-terminal"
    claim = knowledge.claim_next_outbox_event(
        context,
        worker_capability=capability,
        claim_token=claim_token,
        executor_id="worker-terminal",
    )
    assert claim is not None and claim["event_id"] == published_event
    knowledge.mark_outbox_dispatching(
        context,
        published_event,
        worker_capability=capability,
        claim_token=claim_token,
    )
    transport_receipt = {
        "event_id": published_event,
        "payload_digest": claim["payload_digest"],
        "delivery_state": "DELIVERED",
        "provider_message_id": "provider-terminal",
    }
    binding = {
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
        "actor_id": context.actor_id,
        "event_id": published_event,
        "event_type": claim["event_type"],
        "aggregate_id": claim["aggregate_id"],
        "payload_digest": claim["payload_digest"],
        "delivery_state": "DELIVERED",
        "provider_message_id": "provider-terminal",
        "attempt": 1,
        "claim_token_digest": claim["claim_token_digest"],
        "transport_receipt_digest": canonical_digest(transport_receipt),
    }
    receipt = _execution_receipt(binding, executor_id="worker-terminal")
    first = knowledge.mark_outbox_published(
        context,
        published_event,
        worker_capability=capability,
        claim_token=claim_token,
        transport_receipt=transport_receipt,
        delivery_receipt=receipt,
    )
    assert knowledge.mark_outbox_published(
        context,
        published_event,
        worker_capability=capability,
        claim_token=claim_token,
        transport_receipt=transport_receipt,
        delivery_receipt=receipt,
    ) == first
    with pytest.raises(ConflictError, match="KNOWLEDGE_OUTBOX_PUBLICATION_FENCE_CONFLICT"):
        knowledge.mark_outbox_published(
            context,
            published_event,
            worker_capability=capability,
            claim_token="claim-token-drift",
            transport_receipt=transport_receipt,
            delivery_receipt=receipt,
        )
    assert knowledge.outbox_delivery_state(context, published_event)[
        "delivery_phase"
    ] == "PUBLISHED"
    store.close()


def test_explicit_reconciliation_delivered_or_not_delivered_is_the_only_unknown_exit(
    tmp_path: Path,
) -> None:
    store, knowledge, context, capability = _open_scope(tmp_path)
    delivered_event = _create_event(store, knowledge, context, "reconcile-delivered")
    transport = _ControlledTransport("response-loss")
    worker = _worker(knowledge, context, capability, transport, "worker-reconcile")
    with pytest.raises(IntegrityError, match="KNOWLEDGE_OUTBOX_TRANSPORT_OUTCOME_UNKNOWN"):
        worker.run_once()
    delivered_state = knowledge.outbox_delivery_state(context, delivered_event)
    delivered_receipt = _reconciliation_receipt(
        delivered_state,
        delivery_state="DELIVERED",
        reconciliation_id="reconciliation-delivered",
    )
    reconciled = worker.reconcile_outbox_event(delivered_event, delivered_receipt)
    assert reconciled["delivery_phase"] == "PUBLISHED"
    assert worker.reconcile_outbox_event(delivered_event, delivered_receipt) == reconciled
    assert transport.effects == [delivered_event]

    pending_event = _create_event(store, knowledge, context, "reconcile-not-delivered")
    with pytest.raises(IntegrityError, match="KNOWLEDGE_OUTBOX_TRANSPORT_OUTCOME_UNKNOWN"):
        worker.run_once()
    pending_state = knowledge.outbox_delivery_state(context, pending_event)
    not_delivered_receipt = _reconciliation_receipt(
        pending_state,
        delivery_state="NOT_DELIVERED",
        reconciliation_id="reconciliation-not-delivered",
    )
    reopened = worker.reconcile_outbox_event(pending_event, not_delivered_receipt)
    assert reopened["delivery_phase"] == "PENDING"
    transport.mode = "success"
    retried = worker.run_once()
    assert retried["publication_results"][0]["event_id"] == pending_event
    assert knowledge.outbox_delivery_state(context, pending_event)[
        "delivery_phase"
    ] == "PUBLISHED"
    assert transport.effects.count(pending_event) == 2
    store.close()


def test_reconciliation_and_acl_bind_exact_tenant_project_actor_event_and_rebuild(
    tmp_path: Path,
) -> None:
    store, knowledge, context, capability = _open_scope(tmp_path)
    event_id = _create_event(store, knowledge, context, "binding")
    transport = _ControlledTransport("response-loss")
    worker = _worker(knowledge, context, capability, transport, "worker-binding")
    with pytest.raises(IntegrityError):
        worker.run_once()
    state = knowledge.outbox_delivery_state(context, event_id)
    receipt = _reconciliation_receipt(
        state,
        delivery_state="DELIVERED",
        reconciliation_id="reconciliation-binding",
    )
    for key, drift in (
        ("tenant_id", "tenant-other"),
        ("project_id", "project-other"),
        ("actor_id", "actor-other"),
        ("event_id", "kevt-other"),
        ("aggregate_id", "rebuild-other"),
        ("payload_digest", "f" * 64),
    ):
        with pytest.raises(IntegrityError, match="KNOWLEDGE_OUTBOX_RECONCILIATION_BINDING_MISMATCH"):
            worker.reconcile_outbox_event(event_id, {**receipt, key: drift})
        assert knowledge.outbox_delivery_state(context, event_id)[
            "delivery_phase"
        ] == "UNKNOWN"

    other = TenantContext(context.tenant_id, context.project_id, "actor-admin-other")
    store.grant_permissions(
        context,
        other.actor_id,
        [IntakeStore.READ, IntakeStore.WRITE, IntakeStore.ADMIN],
    )
    with pytest.raises(NotFoundError, match="KNOWLEDGE_OUTBOX_EVENT_NOT_FOUND"):
        knowledge.outbox_delivery_state(other, event_id)

    limited = TenantContext(context.tenant_id, context.project_id, "actor-limited")
    store.grant_permissions(
        context,
        limited.actor_id,
        [IntakeStore.READ, IntakeStore.WRITE],
    )
    with pytest.raises(AuthorizationError, match="KNOWLEDGE_PROJECT_ACCESS_DENIED"):
        _worker(knowledge, limited, capability, _ControlledTransport(), "worker-limited")

    authorized_worker = _worker(
        knowledge,
        context,
        capability,
        _ControlledTransport(),
        "worker-revoked",
    )
    with store.transaction() as connection:
        connection.execute(
            """
            DELETE FROM project_acl
             WHERE tenant_id=? AND project_id=? AND principal_id=? AND permission=?
            """,
            (
                context.tenant_id,
                context.project_id,
                context.actor_id,
                IntakeStore.ADMIN,
            ),
        )
    with pytest.raises(AuthorizationError, match="KNOWLEDGE_PROJECT_ACCESS_DENIED"):
        authorized_worker.run_once()
    store.close()
