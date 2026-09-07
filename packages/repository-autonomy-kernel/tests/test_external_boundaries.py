from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from elmos_repository_autonomy.adapters import ADAPTERS, all_local_conformance
from elmos_repository_autonomy.dispatcher import AutonomyRuntime
from elmos_repository_autonomy.errors import KernelError
from elmos_repository_autonomy.external import (
    PROVIDER_PROFILES,
    AdapterOutcome,
    CanonicalSCMAdapter,
    DurableEventPublisher,
    EphemeralSecretsBroker,
    ExternalOperationCoordinator,
    HMACAuthorizationVerifier,
    IdempotentEventConsumer,
    LocalGitSCMAdapter,
    OutcomeStatus,
    S3ObjectStoreAdapter,
    S3PresignService,
    ScriptedExternalAdapter,
    provider_adapters,
)
from elmos_repository_autonomy.storage import DurableStore


def operation_request(**overrides):
    value = {
        "tenant_id": "tenant-a",
        "account_id": "account-a",
        "capability": "provider",
        "adapter_id": "fake-provider",
        "adapter_version": "2.0.0",
        "provider_instance": "provider-test",
        "region": "test-1",
        "native_resource_id": "resource-1",
        "action": "invoke",
        "idempotency_key": "operation-1",
        "side_effects": True,
        "payload": {"input_ref": "artifact:sha256:test"},
    }
    value.update(overrides)
    return value


def signed_grant(operation: dict, key: bytes) -> dict:
    grant = {
        "key_id": "authority-1",
        "issuer": "external-pdp",
        "source": "workload-identity",
        "tenant_id": operation["tenant_id"],
        "account_id": operation["account_id"],
        "capabilities": [operation["capability"]],
        "actions": [operation["action"]],
        "native_resource_ids": [operation["native_resource_id"]],
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
    }
    grant["signature"] = HMACAuthorizationVerifier.sign(grant, key)
    return grant


def test_external_operation_is_authorized_idempotent_and_tenant_isolated():
    key = b"authority-test-key"
    store = DurableStore()
    coordinator = ExternalOperationCoordinator(store, authorizer=HMACAuthorizationVerifier({"authority-1": key}))
    coordinator.register(
        ScriptedExternalAdapter(
            "fake-provider",
            "provider",
            execute_outcome=AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED,
                result={"output_hash": "sha256:result"},
                raw_evidence={"provider_request_id": "provider-op-1"},
                evidence_class="LOCAL_ENGINEERING_VALIDATED",
                side_effect_performed=True,
            ),
        )
    )
    request = operation_request()
    first = coordinator.plan(request)
    second = coordinator.plan(request)
    assert first["operation_id"] == second["operation_id"]
    coordinator.authorize(first["operation_id"], tenant_id="tenant-a", grant=signed_grant(request, key))
    result = coordinator.execute(first["operation_id"], tenant_id="tenant-a")
    assert result["state"] == "EXECUTED"
    assert result["external_evidence"] == "NOT_RUN"
    assert coordinator.execute(first["operation_id"], tenant_id="tenant-a")["state"] == "EXECUTED"
    with pytest.raises(KernelError, match="EXTERNAL_OPERATION_NOT_FOUND"):
        coordinator.get(first["operation_id"], tenant_id="tenant-b")
    with pytest.raises(KernelError, match="IDEMPOTENCY_CONFLICT"):
        coordinator.plan(operation_request(payload={"input_ref": "different"}))


def test_runtime_can_route_wave_state_to_a_separate_control_store():
    runtime_store = DurableStore()
    control_store = DurableStore()
    runtime = AutonomyRuntime(runtime_store, control_store=control_store)
    planned = runtime.external.plan(operation_request(idempotency_key="control-store-1"))
    assert runtime_store.get_external_operation(planned["operation_id"], tenant_id="tenant-a") is None
    assert control_store.get_external_operation(planned["operation_id"], tenant_id="tenant-a") is not None


def test_unknown_side_effect_requires_verified_reconciliation_before_evidence():
    key = b"authority-test-key"
    store = DurableStore()
    coordinator = ExternalOperationCoordinator(
        store,
        authorizer=HMACAuthorizationVerifier({"authority-1": key}),
        receipt_verifier=lambda record: record["verifier_id"] == "independent-verifier",
    )
    coordinator.register(
        ScriptedExternalAdapter(
            "fake-provider",
            "provider",
            execute_outcome=AdapterOutcome(
                status=OutcomeStatus.UNKNOWN,
                raw_evidence={"timeout": True},
                evidence_class="EXTERNAL_EXECUTED",
                side_effect_performed=True,
            ),
            reconcile_outcome=AdapterOutcome(
                status=OutcomeStatus.SUCCEEDED,
                result={"confirmed": True},
                raw_evidence={"provider_lookup": "found"},
                evidence_class="EXTERNAL_EXECUTED",
            ),
        )
    )
    request = operation_request()
    planned = coordinator.plan(request)
    coordinator.authorize(planned["operation_id"], tenant_id="tenant-a", grant=signed_grant(request, key))
    unknown = coordinator.execute(planned["operation_id"], tenant_id="tenant-a")
    assert unknown["state"] == "UNKNOWN"
    assert unknown["external_evidence"] == "NOT_RUN"
    with pytest.raises(KernelError, match="UNKNOWN_OUTCOME_REQUIRES_RECONCILIATION"):
        coordinator.execute(planned["operation_id"], tenant_id="tenant-a")
    reconciled = coordinator.reconcile(
        planned["operation_id"], tenant_id="tenant-a", verifier_id="independent-verifier"
    )
    assert reconciled["state"] == "RECONCILED"
    assert reconciled["external_evidence"] == "INDEPENDENTLY_VERIFIED"


class UnknownThenPublishedBus:
    evidence_class = "INDEPENDENTLY_VERIFIED"

    def publish(self, event):
        return {"status": "UNKNOWN", "raw_evidence": {"timeout": True}}

    def reconcile(self, event):
        return {
            "status": "PUBLISHED",
            "producer_id": "event-provider",
            "verifier_id": "event-auditor",
            "raw_evidence": {"native_event_id": event["event_id"]},
        }


def test_transactional_outbox_blocks_unknown_republish_until_reconciled():
    store = DurableStore()
    event = store.enqueue_outbox(
        tenant_id="tenant-a",
        topic="events",
        ordering_key="repository-1",
        event_type="UPDATED",
        payload={"version": 1},
        idempotency_key="event-1",
    )
    duplicate = store.enqueue_outbox(
        tenant_id="tenant-a",
        topic="events",
        ordering_key="repository-1",
        event_type="UPDATED",
        payload={"version": 1},
        idempotency_key="event-1",
    )
    assert duplicate["event_id"] == event["event_id"]
    publisher = DurableEventPublisher(store, UnknownThenPublishedBus(), receipt_verifier=lambda record: True)
    assert publisher.publish_pending(tenant_id="tenant-a")[0]["state"] == "UNKNOWN"
    assert publisher.publish_pending(tenant_id="tenant-a") == []
    reconciled = publisher.reconcile_unknown(event["event_id"], tenant_id="tenant-a")
    assert reconciled["state"] == "PUBLISHED"
    assert reconciled["external_evidence"] == "INDEPENDENTLY_VERIFIED"


def test_inbox_consumer_deduplicates_success_and_reconciles_unknown_side_effects():
    store = DurableStore()
    consumer = IdempotentEventConsumer(store, "worker-1")
    calls = []
    event = {"event_id": "event-1", "ordering_key": "repo-1", "payload": {"value": 1}}
    first = consumer.consume(
        tenant_id="tenant-a",
        event=event,
        handler=lambda payload: calls.append(payload) or {"status": "done"},
        side_effects=True,
    )
    replay = consumer.consume(
        tenant_id="tenant-a",
        event=event,
        handler=lambda payload: calls.append(payload) or {"status": "duplicate"},
        side_effects=True,
    )
    assert first["state"] == "PROCESSED"
    assert replay["replayed"] is True
    assert len(calls) == 1
    unknown_event = {"event_id": "event-2", "ordering_key": "repo-1", "payload": {"value": 2}}
    unknown = consumer.consume(
        tenant_id="tenant-a",
        event=unknown_event,
        handler=lambda payload: (_ for _ in ()).throw(TimeoutError()),
        side_effects=True,
    )
    assert unknown["state"] == "UNKNOWN"
    with pytest.raises(KernelError, match="EVENT_RECONCILIATION_REQUIRED"):
        consumer.consume(
            tenant_id="tenant-a", event=unknown_event,
            handler=lambda payload: {"status": "must-not-run"}, side_effects=True,
        )
    reconciled = consumer.reconcile(
        tenant_id="tenant-a",
        event_id="event-2",
        processed=False,
        evidence={"receipt": "provider-not-published"},
        verifier=lambda evidence: evidence.get("receipt") == "provider-not-published",
    )
    assert reconciled["state"] == "RETRY"


def test_secret_lease_material_is_ephemeral_and_zeroized():
    store = DurableStore()
    broker = EphemeralSecretsBroker(store, "test-broker", lambda ref: b"not-persisted-secret")
    handle = broker.lease(
        tenant_id="tenant-a", secret_ref="secret://provider/key", scope={"operation_id": "op-1"}
    )
    assert handle.reveal() == b"not-persisted-secret"
    lease_id = str(handle.lease["lease_id"])
    persisted = store._connection.execute("select * from secret_leases where lease_id=?", (lease_id,)).fetchone()
    assert "not-persisted-secret" not in repr(dict(persisted))
    broker.revoke(lease_id, tenant_id="tenant-a")
    assert bytes(handle._material) == b"\x00" * len(b"not-persisted-secret")
    with pytest.raises(KernelError, match="SECRET_LEASE_EXPIRED"):
        handle.reveal()


def test_seven_provider_profiles_have_exactly_84_local_engineering_units():
    report = all_local_conformance()
    assert set(PROVIDER_PROFILES) == set(ADAPTERS)
    assert report["adapter_count"] == 7
    assert report["conformance_unit_count"] == 84
    assert report["engineering_status"] == "PASS"
    assert report["status"] == "BLOCKED"
    assert report["external_evidence"] == "NOT_RUN"


def test_local_git_adapter_resolves_an_exact_commit_without_network(tmp_path):
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    (repository / "README.md").write_text("test\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repository), "-c", "user.name=Kernel Test",
            "-c", "user.email=kernel@example.invalid", "commit", "-q", "-m", "test",
        ],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    adapter = LocalGitSCMAdapter([str(tmp_path)])
    result = adapter.execute(
        {"action": "resolve-exact-commit"}, {"repository_path": str(repository), "commit": commit}
    )
    assert result.status == OutcomeStatus.SUCCEEDED
    assert result.result["commit"] == commit
    assert result.evidence_class == "LOCAL_ENGINEERING_VALIDATED"


class FakeSCMTransport:
    evidence_class = "LOCAL_ENGINEERING_VALIDATED"

    def invoke(self, request):
        return {
            "status": "SUCCEEDED",
            "result": {
                "exact_commit": request["exact_commit"],
                "workspace_complete": True,
                "submodules_verified": True,
                "lfs_verified": True,
                "sparse_hydrated": True,
            },
            "raw_evidence": {"provider_request_id": "scm-local-1"},
            "native_operation_id": "scm-local-1",
        }


def test_remote_scm_spi_requires_exact_commit_and_complete_hydration():
    adapter = CanonicalSCMAdapter(FakeSCMTransport(), adapter_id="github-enterprise")
    outcome = adapter.execute(
        {
            "action": "hydrate-workspace",
            "provider_instance": "github-enterprise-1",
            "native_resource_id": "repository-42",
            "region": "global",
            "idempotency_key": "hydrate-1",
        },
        {
            "exact_commit": "a" * 40,
            "credential_lease_ref": "lease://scm/read-1",
            "submodules": True,
            "lfs": True,
            "sparse_paths": ["src", "tests"],
        },
    )
    assert outcome.status == OutcomeStatus.SUCCEEDED
    assert outcome.result["workspace_complete"] is True
    with pytest.raises(KernelError, match="SCM_COMMIT_INVALID"):
        adapter.execute(
            {
                "action": "resolve-exact-commit", "provider_instance": "github-enterprise-1",
                "native_resource_id": "repository-42", "region": "global", "idempotency_key": "resolve-1",
            },
            {"exact_commit": "main", "credential_lease_ref": "lease://scm/read-1"},
        )


class FakeS3:
    evidence_class = "LOCAL_ENGINEERING_VALIDATED"

    def invoke(self, request):
        if request["action"] == "presign":
            return {
                "status": "SUCCEEDED",
                "result": {
                    "url": "https://object.example.invalid/signed?redacted=true",
                    "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
                },
                "native_operation_id": "s3-presign-local-1",
            }
        return {
            "status": "SUCCEEDED",
            "result": {"read_back_hash": request["content_hash"], "content_hash": request["content_hash"]},
            "raw_evidence": {"request_id": "s3-local-1"},
            "native_operation_id": "s3-local-1",
            "side_effect_performed": True,
        }


class FakeProviderTransport:
    evidence_class = "LOCAL_ENGINEERING_VALIDATED"

    def __init__(self):
        self.envelopes = []

    def invoke(self, adapter_id, envelope):
        self.envelopes.append((adapter_id, dict(envelope)))
        return {
            "status": "SUCCEEDED",
            "result": {"output_hash": "sha256:result"},
            "raw_evidence": {"request_id": "provider-local-1"},
        }


def test_s3_and_seven_provider_spis_use_exact_canonical_envelopes():
    s3 = S3ObjectStoreAdapter(FakeS3())
    object_result = s3.execute(
        {
            "account_id": "account-a", "region": "us-test-1", "native_resource_id": "bucket-a",
            "action": "put", "idempotency_key": "put-1",
        },
        {
            "key": "tenant/object.bin",
            "content": b"object-bytes",
            "secret_ref": "lease://s3",
            "server_side_encryption": "aws:kms",
            "kms_key_ref": "kms://test/key-1",
        },
    )
    assert object_result.status == OutcomeStatus.SUCCEEDED
    assert "content" not in object_result.result
    presigned = S3PresignService(FakeS3()).issue(
        tenant_id="tenant-a",
        account_id="account-a",
        region="us-test-1",
        bucket="bucket-a",
        key="tenant-a/object.bin",
        method="PUT",
        ttl_seconds=300,
        content_hash="sha256:" + "a" * 64,
    )
    assert presigned.reveal().startswith("https://")
    assert presigned.evidence["url_persisted"] is False
    transport = FakeProviderTransport()
    adapters = provider_adapters(transport)
    assert len(adapters) == 7
    outcome = adapters[0].execute(
        {
            "idempotency_key": "provider-1", "action": "invoke", "provider_instance": "provider-test",
            "region": "test-1", "authority_hash": "sha256:authority", "side_effects": False,
        },
        {"input_ref": "artifact:sha256:test"},
    )
    assert outcome.status == OutcomeStatus.SUCCEEDED
    assert transport.envelopes[0][1]["schema_version"] == "2.0.0"
    assert transport.envelopes[0][1]["authority"]["digest"] == "sha256:authority"
