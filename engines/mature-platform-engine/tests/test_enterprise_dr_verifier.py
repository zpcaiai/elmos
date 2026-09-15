"""Unit tests for enterprise_dr_verifier.py."""

import pytest
from elmos_mature_platform.enterprise_dr_verifier import (
    DrRehearsalConfig,
    EnterpriseDrVerifier,
    compute_merkle_root,
)


def test_compute_merkle_root_empty():
    root = compute_merkle_root([])
    assert isinstance(root, str)
    assert len(root) == 64


def test_compute_merkle_root_single():
    h = "a" * 64
    root = compute_merkle_root([h])
    assert root == h


def test_compute_merkle_root_multiple():
    leaves = [f"{i:064x}" for i in range(4)]
    root1 = compute_merkle_root(leaves)
    root2 = compute_merkle_root(leaves)
    assert root1 == root2
    assert len(root1) == 64

    # Order alteration alters root
    root_shuffled = compute_merkle_root(list(reversed(leaves)))
    assert root1 != root_shuffled


def test_enterprise_dr_rehearsal_execution():
    config = DrRehearsalConfig(
        tenant_id="tenant-test-dr",
        service_name="ledger-test-service",
        primary_region="region-alpha",
        secondary_regions=["region-beta"],
        rto_target_seconds=10.0,
        rpo_target_seconds=5.0,
        workload_size=100,
        inject_network_jitter_ms=1.0,
    )
    verifier = EnterpriseDrVerifier(config)
    result = verifier.run_rehearsal()

    assert result.status == "PASSED"
    assert result.tenant_id == "tenant-test-dr"
    assert result.primary_region == "region-alpha"
    assert result.failover_region == "region-beta"
    assert result.merkle_integrity_passed is True
    assert result.transaction_loss_count == 0
    assert result.rto_seconds > 0.0
    assert result.rto_passed is True
    assert result.rpo_passed is True
    assert result.fencing_token_validated is True
    assert result.quorum_consensus_achieved is True
    assert len(result.log_traces) > 5

    # Check evidence receipt contract
    receipt = result.evidence_receipt
    assert receipt["evidence_type"] == "ENTERPRISE_DR_REHEARSAL_RECEIPT_V1"
    assert receipt["execution_authority"] == "LOCAL_EXECUTED_SELF_ATTESTED"
    assert receipt["third_party_independent_certification"] == "NOT_RUN"
    assert receipt["metrics"]["transactions_lost"] == 0
    assert receipt["metrics"]["merkle_integrity_passed"] is True
