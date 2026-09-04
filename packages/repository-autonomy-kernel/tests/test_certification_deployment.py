from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

import pytest

from elmos_repository_autonomy.certification import (
    T06_TEST_CASES,
    TEST_CASES,
    CertificationEngine,
    EvidenceTrustStore,
    TrustAnchor,
    evaluate_p05,
)
from elmos_repository_autonomy.deployment import (
    KubernetesAdapter,
    KubernetesFailureAdapter,
    deployment_evidence_status,
)
from elmos_repository_autonomy.errors import KernelError
from elmos_repository_autonomy.golden import CustomerAcceptanceRegistry, GoldenRouteEvaluator
from elmos_repository_autonomy.postgres import PostgresDisasterRecovery, PostgresMigrationRunner, PostgresSessionFactory
from elmos_repository_autonomy.postgres_wave_store import PostgresWaveStore
from elmos_repository_autonomy.storage import DurableStore


def repository_binding(**overrides):
    value = {
        "tenant_id": "tenant-a",
        "provider_instance": "github-enterprise-1",
        "native_repository_id": "repo-42",
        "exact_commit": "a" * 40,
        "corpus_class": "holdout",
        "authorization_receipt": "sha256:" + "9" * 64,
        "purpose": "acceptance",
        "retention_policy": "delete-after-30-days",
        "customer_actor_id": "customer-actor",
    }
    value.update(overrides)
    return value


def test_t00_t08_matrix_contains_all_84_provider_units_and_starts_not_certified():
    assert len(T06_TEST_CASES) == 84
    assert len(TEST_CASES) == 125
    result = CertificationEngine(DurableStore()).evaluate(
        tenant_id="tenant-a", candidate_digest="sha256:" + "a" * 64, release_context={}
    )
    assert result["matrix"]["t06_conformance_units"] == 84
    assert result["levels"]["E1"]["status"] == "NOT_RUN"
    assert result["p05"]["issued"] is False
    assert result["certification"] == "NOT_CERTIFIED"


def test_external_certification_evidence_without_trust_anchor_is_rejected():
    engine = CertificationEngine(DurableStore())
    record = {
        "tenant_id": "tenant-a",
        "case_id": T06_TEST_CASES[0].case_id,
        "status": "PASS",
        "evidence_class": "INDEPENDENTLY_VERIFIED",
        "source_kind": "real-provider",
        "producer_id": "provider",
        "verifier_id": "verifier",
        "independent": True,
        "key_id": "untrusted",
        "signature": "fabricated",
        "payload": {
            "authorization_receipt": {
                "receipt_hash": "sha256:" + "a" * 64,
                "scope_hash": "sha256:" + "b" * 64,
            },
            "raw_artifacts": [
                {"artifact_ref": "object://evidence", "content_hash": "sha256:" + "c" * 64}
            ],
            "replay": {"command_digest": "sha256:" + "d" * 64, "status": "PASS"},
            "environment": {"id": "external", "digest": "sha256:" + "e" * 64},
        },
    }
    with pytest.raises(KernelError, match="EXTERNAL_EVIDENCE_INVALID"):
        engine.ingest(tenant_id="tenant-a", record=record)


def test_external_evidence_is_reverified_against_current_anchor_revocation():
    key = b"independent-verifier-test-key"
    store = DurableStore()
    trusted = EvidenceTrustStore(
        {"verifier-key": TrustAnchor(key=key, subject_id="independent-verifier")}
    )
    record = {
        "tenant_id": "tenant-a",
        "case_id": T06_TEST_CASES[0].case_id,
        "status": "PASS",
        "evidence_class": "INDEPENDENTLY_VERIFIED",
        "source_kind": "real-provider",
        "producer_id": "provider-executor",
        "verifier_id": "independent-verifier",
        "independent": True,
        "key_id": "verifier-key",
        "captured_at": datetime.now(UTC).isoformat(),
        "payload": {
            "authorization_receipt": {
                "receipt_hash": "sha256:" + "a" * 64,
                "scope_hash": "sha256:" + "b" * 64,
            },
            "raw_artifacts": [
                {"artifact_ref": "object://evidence", "content_hash": "sha256:" + "c" * 64}
            ],
            "replay": {"command_digest": "sha256:" + "d" * 64, "status": "PASS"},
            "environment": {"id": "external", "digest": "sha256:" + "e" * 64},
        },
    }
    record["signature"] = trusted.sign(record, key)
    CertificationEngine(store, trusted).ingest(tenant_id="tenant-a", record=record)

    revoked = EvidenceTrustStore(
        {"verifier-key": TrustAnchor(key=key, subject_id="independent-verifier", revoked=True)}
    )
    result = CertificationEngine(store, revoked).evaluate(
        tenant_id="tenant-a", candidate_digest="sha256:" + "f" * 64, release_context={}
    )
    case_result = next(
        item for item in result["matrix"]["case_results"] if item["case_id"] == record["case_id"]
    )
    assert case_result["status"] == "BLOCKED"
    assert result["p05"]["issued"] is False


def test_local_t00_can_reach_e1_engineering_pass_but_not_external_certification():
    engine = CertificationEngine(DurableStore())
    payload = {
        "raw_artifacts": [
            {"artifact_ref": "local://pytest", "content_hash": "sha256:" + "a" * 64}
        ],
        "replay": {"command_digest": "sha256:" + "b" * 64, "status": "PASS"},
        "environment": {"id": "local-python", "digest": "sha256:" + "c" * 64},
    }
    for case in (item for item in TEST_CASES if item.suite_id == "T00"):
        engine.ingest(
            tenant_id="tenant-a",
            record={
                "tenant_id": "tenant-a",
                "case_id": case.case_id,
                "status": "PASS",
                "evidence_class": "LOCAL_ENGINEERING_VALIDATED",
                "source_kind": "repository-test",
                "producer_id": "pytest",
                "independent": False,
                "payload": payload,
            },
        )
    result = engine.evaluate(
        tenant_id="tenant-a", candidate_digest="sha256:" + "d" * 64, release_context={}
    )
    assert result["levels"]["E1"]["status"] == "PASS"
    assert result["levels"]["E2"]["status"] == "NOT_RUN"
    assert result["p05"]["issued"] is False
    assert result["certification"] == "NOT_CERTIFIED"


def test_p05_ignores_completion_claim_and_requires_all_hard_evidence():
    levels = {level: {"status": "PASS"} for level in ("E1", "E2", "E3", "E4", "E5")}
    result = evaluate_p05(levels, {"completion_claim": "P05_DEPLOYMENT_COMPLETE"})
    assert result["issued"] is False
    assert result["completion_claim_ignored"] is True
    assert "deployment-evidence" in result["reasons"]
    assert result["decision"] == "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED"


def test_p05_rejects_provider_evidence_relabelled_as_release_or_customer_evidence():
    levels = {level: {"status": "PASS"} for level in ("E1", "E2", "E3", "E4", "E5")}
    candidate_digest = "sha256:" + "a" * 64
    evidence_id = "provider-evidence"
    provider_record = {
        "evidence_id": evidence_id,
        "case_id": T06_TEST_CASES[0].case_id,
        "status": "PASS",
        "evidence_class": "INDEPENDENTLY_VERIFIED",
        "producer_id": "provider",
        "verifier_id": "verifier",
        "content_hash": "sha256:" + "b" * 64,
        "payload": {
            "approval": {
                "decision": "APPROVED",
                "scope": "release",
                "candidate_digest": candidate_digest,
            },
            "deployment": {"status": "PASS", "candidate_digest": candidate_digest},
        },
    }
    reference = {
        "evidence_id": evidence_id,
        "producer_id": "provider",
        "verifier_id": "verifier",
        "content_hash": provider_record["content_hash"],
    }
    result = evaluate_p05(
        levels,
        {
            "health": {"livez": True, "readyz": True, "metrics": True, "version": True},
            "rollback_ready": True,
            "restore_replayed": True,
            "open_findings": [],
            "artifacts": [
                {"content_hash": "sha256:" + "c" * 64, "integrity_verified": True}
            ],
            "independent_approvals": [reference],
            "deployment_evidence": [reference],
            "customer_acceptance": {
                "acceptance_id": "acceptance-1",
                "decision": "ACCEPTED",
                "signature_verified": True,
                "customer_actor_id": "customer",
                "executor_id": "executor",
                "evidence_ids": [evidence_id],
            },
        },
        verified_evidence_ids=frozenset({evidence_id}),
        verified_evidence={evidence_id: provider_record},
        customer_acceptances=(
            {
                "acceptance_id": "acceptance-1",
                "candidate_digest": candidate_digest,
                "decision": "ACCEPTED",
                "signature_verified": True,
                "customer_actor_id": "customer",
                "executor_id": "executor",
                "evidence_ids": [evidence_id],
            },
        ),
        candidate_digest=candidate_digest,
    )
    assert result["issued"] is False
    assert {"independent-approval", "deployment-evidence", "customer-acceptance"}.issubset(
        result["reasons"]
    )


def test_customer_acceptance_rejects_self_approval_and_golden_route_needs_both_corpora():
    registry = CustomerAcceptanceRegistry(DurableStore())
    with pytest.raises(KernelError, match="SELF_APPROVAL_DENIED"):
        registry.record(
            binding=repository_binding(customer_actor_id="executor"),
            route_id="repository-scale-refactor",
            candidate_digest="sha256:" + "a" * 64,
            executor_id="executor",
            decision={"decision": "ACCEPTED", "evidence_ids": ["e1"], "signature_verified": True},
            authenticated_customer_actor_id="executor",
        )
    with pytest.raises(KernelError, match="ACCEPTANCE_EVIDENCE_MISSING"):
        registry.record(
            binding=repository_binding(),
            route_id="repository-scale-refactor",
            candidate_digest="sha256:" + "a" * 64,
            executor_id="executor",
            decision={"decision": "ACCEPTED", "evidence_ids": ["e1"], "signature_verified": True},
            authenticated_customer_actor_id="customer-actor",
        )
    evidence = {
        "baseline": {"build": "PASS", "test": "PASS", "contract": "PASS", "security": "PASS"},
        "source_snapshot_digest": "sha256:source",
        "target_commit": "b" * 40,
        "semantic_ir_digest": "sha256:ir",
        "change_graph_digest": "sha256:graph",
        "validation_dag_digest": "sha256:validation",
        "artifact_graph_digest": "sha256:artifacts",
        "rollback_receipt": "rollback",
        "cost_eta_slo": {"status": "PASS"},
        "validation_results": [{"status": "PASS"}],
        "unknown_semantics": [],
        "customer_acceptance": {
            "decision": "ACCEPTED",
            "signature_verified": True,
            "customer_actor_id": "customer-actor",
            "evidence_ids": ["acceptance-evidence"],
        },
    }
    route = GoldenRouteEvaluator().evaluate(
        binding=repository_binding(), route_id="repository-scale-refactor",
        candidate_digest="sha256:" + "b" * 64, evidence=evidence, executor_id="executor",
    )
    assert route["status"] == "BLOCKED"
    assert "representative" in route["missing"]
    assert route["external_evidence"] == "NOT_RUN"


class FakeKubectl:
    evidence_class = "LOCAL_ENGINEERING_VALIDATED"

    def __init__(self):
        self.calls = []

    def run(self, argv, *, timeout_seconds):
        self.calls.append((list(argv), timeout_seconds))
        return {"returncode": 0, "stdout": "ok", "stderr": "", "argv_digest": "sha256:argv"}


def test_kubernetes_apply_requires_authorized_mode_digest_and_matching_manifest(tmp_path):
    digest_image = "registry.example/elmos@sha256:" + "a" * 64
    manifest = tmp_path / "deployment.yaml"
    manifest.write_text(
        f"apiVersion: apps/v1\nkind: Deployment\nspec:\n  template:\n    spec:\n      containers:\n        - name: app\n          image: {digest_image}\n",
        encoding="utf-8",
    )
    operation = {"action": "apply"}
    payload = {
        "manifest_path": str(manifest),
        "image": digest_image,
        "approved_isolated_environment": True,
        "owner": "release-owner",
        "budget": {"currency": "USD", "amount": "10"},
        "cleanup_ttl_minutes": 30,
    }
    dry_only = KubernetesAdapter(
        context="isolated-test", namespace="elmos-test", allowed_manifest_roots=[str(tmp_path)],
        runner=FakeKubectl(), execution_mode="dry-run",
    )
    assert dry_only.execute(operation, payload).status.value == "NOT_RUN"
    runner = FakeKubectl()
    enabled = KubernetesAdapter(
        context="isolated-test", namespace="elmos-test", allowed_manifest_roots=[str(tmp_path)],
        runner=runner, execution_mode="apply",
    )
    assert enabled.execute(operation, payload).status.value == "SUCCEEDED"
    assert runner.calls[0][0][:5] == ["kubectl", "--context", "isolated-test", "--namespace", "elmos-test"]
    with pytest.raises(KernelError, match="KUBERNETES_IMAGE_MISMATCH"):
        enabled.execute(operation, {**payload, "image": "registry.example/other@sha256:" + "b" * 64})
    chaos = KubernetesFailureAdapter(enabled)
    injected = chaos.execute(
        {"action": "inject-failure"},
        {
            "scenario_id": "pod-crash",
            "pod": "kernel-abc123",
            "deployment": "kernel",
            "approved_isolated_environment": True,
            "experiment_owner": "resilience-owner",
            "cleanup_ttl_minutes": 15,
            "cleanup_authorized": True,
        },
    )
    assert injected.status.value == "SUCCEEDED"
    assert injected.result["steady_state_oracle"] == "replacement-ready"
    recovered = chaos.compensate({"compensation_token": injected.compensation_token})
    assert recovered.status.value == "SUCCEEDED"


def test_deployment_evidence_requires_failure_scenarios_and_independent_verifier():
    result = deployment_evidence_status({"health": {"livez": True, "readyz": True, "metrics": True, "version": True}})
    assert result["status"] == "BLOCKED"
    assert "failure-scenarios" in result["missing"]
    assert result["external_evidence"] == "NOT_RUN"


class NoConnection:
    def __call__(self):
        raise AssertionError("inventory must not connect")


class FakePgResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakePgConnection:
    def __init__(self):
        self.settings = {}
        self.closed = False
        self.queries = []

    def transaction(self):
        return nullcontext()

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if "set_config('app.tenant_id'" in query:
            self.settings["tenant"] = params[0]
        if "set_config('app.account_id'" in query:
            self.settings["account"] = params[0]
        if "current_setting('app.tenant_id'" in query:
            return FakePgResult(
                {"tenant_setting": self.settings["tenant"], "account_setting": self.settings["account"]}
            )
        if query.startswith("insert into autonomy_external_operations"):
            return FakePgResult(
                {
                    "operation_id": params[0],
                    "tenant_id": params[1],
                    "account_id": params[2],
                    "state": "DRY_RUN",
                    "request_hash": params[-2],
                }
            )
        return FakePgResult()

    def close(self):
        self.closed = True


class FakePgRunner:
    evidence_class = "LOCAL_ENGINEERING_VALIDATED"

    def __init__(self, root: Path):
        self.root = root

    def run(self, argv, *, environment, timeout_seconds):
        del environment, timeout_seconds
        file_arg = next((item for item in argv if item.startswith("--file=")), None)
        if file_arg:
            Path(file_arg.split("=", 1)[1]).write_bytes(b"pg-dump")
        return {"returncode": 0, "argv_digest": "sha256:argv"}


def test_postgres_migrations_are_exact_and_restore_is_disposable_only(tmp_path):
    migration_root = Path(__file__).parents[1] / "sql" / "migrations"
    sessions = PostgresSessionFactory(connect=NoConnection())
    inventory = PostgresMigrationRunner(sessions, str(migration_root)).inventory()
    # V007 is the merged kernel core's stream tables.  They are additive: the
    # control plane's own tables (V001-V006) are untouched, because the kernel
    # core's log is chain-verified and keyed by an arbitrary stream id, which
    # autonomy_events cannot express without changing released schema.
    #
    # V008 adds COMMENT ON TABLE to the 23 tables the migrations create and
    # nothing writes - autonomy_events and autonomy_runs among them.  The
    # earlier note here called unifying the two logs "consolidation debt"; that
    # framing was wrong.  There is no second live log to unify with: nothing in
    # this package writes autonomy_events, or autonomy_runs, the root the other
    # 22 foreign-key to.  See sql/README.md and tests/test_persistence_split.py.
    assert [row.version for row in inventory] == [1, 2, 3, 4, 5, 6, 7, 8]
    recovery = PostgresDisasterRecovery(allowed_backup_root=str(tmp_path), runner=FakePgRunner(tmp_path))
    backup = recovery.backup(
        service_name="elmos-test", backup_path="daily.dump", authorization_receipt="sha256:" + "a" * 64
    )
    assert backup["backup_hash"].startswith("sha256:")
    with pytest.raises(KernelError, match="RESTORE_TARGET_DENIED"):
        recovery.restore(
            service_name="elmos-test", backup_path="daily.dump", authorization_receipt="sha256:" + "b" * 64,
            disposable_target=False, replay_validator=lambda: {"status": "PASS", "raw_evidence": {}},
        )


def test_postgres_wave_store_binds_rls_identity_before_persisting():
    connection = FakePgConnection()
    sessions = PostgresSessionFactory(connect=lambda: connection)
    store = PostgresWaveStore(sessions)
    tenant_id = "11111111-1111-1111-1111-111111111111"
    account_id = "22222222-2222-2222-2222-222222222222"
    operation = store.create_external_operation(
        tenant_id=tenant_id,
        account_id=account_id,
        capability="provider",
        adapter_id="openai-codex",
        adapter_version="2.0.0",
        provider_instance="provider-test",
        region="test-1",
        native_resource_id="provider-resource-1",
        action="invoke",
        side_effects=True,
        idempotency_key="postgres-operation-1",
        request_hash="sha256:" + "a" * 64,
        request_metadata={"input_ref": "artifact://input"},
    )
    assert operation["state"] == "DRY_RUN"
    assert connection.settings == {"tenant": tenant_id, "account": account_id}
    assert any("set_config('row_security', 'on'" in query for query, _ in connection.queries)
    assert connection.closed is True
