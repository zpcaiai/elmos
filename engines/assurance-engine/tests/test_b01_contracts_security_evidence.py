"""Tests for B01: Contracts, Security Isolation, Budget, and Evidence Graph."""

import base64
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from elmos_assurance_engine.contracts import (
    GateDecision,
    RevisionSet,
    canonical_json_bytes,
)
from elmos_assurance_engine.evidence_graph import (
    EvidenceBlob,
    EvidenceEnvelope,
    EvidenceGraph,
    TrustedKey,
)
from elmos_assurance_engine.oracles import RequirementOracle
from elmos_assurance_engine.router_budget import BudgetExhaustedError, ResourceBudget
from elmos_assurance_engine.security_isolation import (
    CapabilityLease,
    DurableExecutionSession,
    VerifiedSecurityContext,
)


def test_b01_revision_set_requires_64_char_hex():
    dummy = "0" * 64
    rev = RevisionSet(
        source=dummy, target=dummy, artifact=dummy, scope=dummy, contract=dummy,
        policy=dummy, environment=dummy, toolchain=dummy, suite=dummy,
        data=dummy, comparator=dummy, rules=dummy,
    )
    assert len(rev.digest()) == 64

    with pytest.raises(ValueError, match="INVALID_SHA256_DIGEST"):
        RevisionSet(
            source="invalid_hex", target=dummy, artifact=dummy, scope=dummy, contract=dummy,
            policy=dummy, environment=dummy, toolchain=dummy, suite=dummy,
            data=dummy, comparator=dummy, rules=dummy,
        )


def test_b01_canonical_json_rejects_floats():
    with pytest.raises(ValueError, match="FLOAT_NOT_ALLOWED"):
        canonical_json_bytes({"price": 19.99})


def test_b01_capability_lease_expiration_and_ceiling():
    now = int(time.time())
    lease = CapabilityLease(
        lease_id="lease-1",
        tenant_id="tenant-a",
        permissions=frozenset({"repo:read", "repo:transform"}),
        ceiling=frozenset({"repo:read", "repo:transform"}),
        expires_at=now + 100,
    )
    assert lease.is_valid(now, "repo:read") is True
    assert lease.is_valid(now, "admin:deploy") is False
    assert lease.is_valid(now + 200, "repo:read") is False  # expired


def test_b01_durable_execution_idempotency_and_fencing():
    ctx = VerifiedSecurityContext(
        tenant_id="t1", project_id="p1", actor_id="a1", run_id="r1", fencing_generation=2
    )
    session = DurableExecutionSession("t1", "r1", ctx)

    # Stale generation rejected
    with pytest.raises(ValueError, match="FENCING_GENERATION_REJECTED"):
        session.commit_idempotent_step("step-1", "idem-1", fencing_generation=1, result_payload={"ok": True})

    # Valid commit
    rec1 = session.commit_idempotent_step("step-1", "idem-1", fencing_generation=2, result_payload={"ok": True})
    # Idempotent replay
    rec2 = session.commit_idempotent_step("step-1", "idem-1", fencing_generation=2, result_payload={"ok": True})
    assert rec1 == rec2

    # Cancellation prevents new commits
    session.request_cancellation()
    with pytest.raises(ValueError, match="EXECUTION_CANCELLED"):
        session.commit_idempotent_step("step-2", "idem-2", fencing_generation=3, result_payload={"ok": True})


def test_b01_router_budget_exhaustion():
    budget = ResourceBudget(max_tokens=1000, max_cost_cents=100)
    budget.consume(tokens=500, cost_cents=50, wall_seconds=1.0)
    assert budget.check_status()[0] == GateDecision.PASS

    with pytest.raises(BudgetExhaustedError, match="TOKEN_BUDGET_EXHAUSTED"):
        budget.consume(tokens=600, cost_cents=0, wall_seconds=1.0)


def test_b01_evidence_envelope_signature_and_invalidation():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    pub_b64 = base64.b64encode(pub.public_bytes_raw()).decode("ascii")

    trusted_keys = {
        "key-1": TrustedKey("key-1", pub_b64, "assurance-domain")
    }

    now = int(time.time())
    rev_digest = "a" * 64
    blob_content = b'{"tests_passed": 10}'
    blob = EvidenceBlob(blob_content)
    blobs = {blob.digest: blob_content}

    payload = {
        "evidence_id": "ev-1",
        "kind": "regression",
        "tenant_id": "t1",
        "project_id": "p1",
        "run_id": "r1",
        "revision_set_digest": rev_digest,
        "report_digest": blob.digest,
        "issued_at": now - 10,
        "expires_at": now + 3600,
    }
    canonical_bytes = canonical_json_bytes(payload)
    sig = base64.b64encode(priv.sign(canonical_bytes)).decode("ascii")

    env = EvidenceEnvelope(
        envelope_id="env-1",
        key_id="key-1",
        algorithm="Ed25519",
        signature_base64=sig,
        payload=payload,
    )

    ok, reasons = env.verify(trusted_keys, blobs, rev_digest, now)
    assert ok is True
    assert reasons == []

    # Tampered blob detected
    blobs_tampered = {blob.digest: b'{"tampered": true}'}
    ok_tampered, reasons_tampered = env.verify(trusted_keys, blobs_tampered, rev_digest, now)
    assert ok_tampered is False
    assert any("REPORT_DIGEST_MISMATCH" in r for r in reasons_tampered)

    # Invalidation DAG test
    dag = EvidenceGraph(rev_digest)
    dag.add_envelope(env)
    # Child envelope depending on ev-1
    dag.dependencies["ev-child"] = {"ev-1"}
    invalidated = dag.invalidate_node("ev-1")
    assert "ev-1" in invalidated
    assert "ev-child" in invalidated


def test_b01_independent_requirement_oracle_catches_deleted_logic():
    oracle = RequirementOracle({
        "obl:payment": {
            "expected_status": 200,
            "required_fields": ["transaction_id", "status"],
            "invariant": "non_negative_balance",
        }
    })
    # Valid
    dec, msg = oracle.evaluate_response("obl:payment", {"status_code": 200, "body": {"transaction_id": "tx1", "status": "CONFIRMED", "balance": 50}})
    assert dec == GateDecision.PASS

    # Negative balance invariant violation
    dec_neg, msg_neg = oracle.evaluate_response("obl:payment", {"status_code": 200, "body": {"transaction_id": "tx1", "status": "CONFIRMED", "balance": -10}})
    assert dec_neg == GateDecision.FAIL
    assert "INVARIANT_VIOLATION" in msg_neg
