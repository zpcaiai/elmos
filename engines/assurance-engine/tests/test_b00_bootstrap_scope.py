"""Tests for B00: Bootstrap and Scope validation."""

from pathlib import Path

import pytest

from elmos_assurance_engine.bootstrap import RepositoryBootstrap
from elmos_assurance_engine.contracts import GateDecision
from elmos_assurance_engine.scope import AssuranceScope, ScopeCompiler


def test_b00_bootstrap_k8_signer_reuse_a01():
    """A01: Reuses existing K8 signer interface without creating bypass."""
    root = Path(__file__).resolve().parents[3]
    b = RepositoryBootstrap(root)
    k8 = b.discover_k8_signer()
    assert k8["status"] in ("REUSE", "AVAILABLE")
    assert k8["bypass_permitted"] is False
    assert k8["signer_boundary"] == "EXTERNAL_ASYMMETRIC_SIGNER_ONLY"


def test_b00_bootstrap_missing_tool_is_not_run_a02():
    """A02: Missing sources or unrun tools default to NOT_RUN."""
    root = Path(__file__).resolve().parents[3]
    b = RepositoryBootstrap(root)
    tools = b.discover_native_toolchains()
    assert "lean" in tools
    # If lean is not installed in machine PATH, it MUST be NOT_RUN, never marked AVAILABLE or COMPLETED
    if not tools["lean"]["available"]:
        assert tools["lean"]["status"] == "NOT_RUN"


def test_b00_bootstrap_compatibility_map_preserves_historical_a03():
    """A03: Explicit profile migration mapping; historical certificates preserved."""
    root = Path(__file__).resolve().parents[3]
    b = RepositoryBootstrap(root)
    compat = b.generate_compatibility_map()
    assert compat["target_profile"] == "elmos.assurance/v4"
    assert compat["historical_profiles_preserved"] is True
    assert compat["historical_certificates"] == "PRESERVED_IMMUTABLE"
    assert "E0" in compat["level_mappings"]
    assert "E5" in compat["level_mappings"]


def test_b00_scope_mandatory_claims_generation_a01():
    """A01: Supported order-permission-flow generates mandatory claims."""
    scope = ScopeCompiler.compile_scope(
        tenant_id="tenant-1",
        project_id="proj-1",
        run_id="run-1",
        supported_features=["order-permission-flow"],
    )
    assert "claim:order-auth-dominance" in scope.mandatory_claims
    assert "claim:order-permission-flow:conformance" in scope.mandatory_claims
    assert len(scope.digest()) == 64


def test_b00_scope_empty_or_deleted_claims_rejected_a02():
    """A02: Empty scope or deleting critical claims results in REJECT / INCONCLUSIVE."""
    with pytest.raises(ValueError, match="EMPTY_SCOPE_REJECTED"):
        ScopeCompiler.compile_scope(
            tenant_id="tenant-1",
            project_id="proj-1",
            run_id="run-1",
            supported_features=[],
        )

    scope = ScopeCompiler.compile_scope(
        tenant_id="tenant-1",
        project_id="proj-1",
        run_id="run-1",
        supported_features=["order-permission-flow", "payment-idempotency"],
    )
    # Valid initial check
    decision, reasons = ScopeCompiler.validate_approved_scope(scope, scope.digest(), frozen_denominator=len(scope.mandatory_claims))
    assert decision == GateDecision.PASS

    # Now simulate reduced claim count against frozen denominator
    reduced_scope = AssuranceScope(
        tenant_id="tenant-1",
        project_id="proj-1",
        run_id="run-1",
        target_profile="elmos.assurance/v4",
        supported_features=("order-permission-flow",),
        exclusions=(),
        mandatory_claims=("claim:order-auth-dominance",),
    )
    dec, reasons = ScopeCompiler.validate_approved_scope(reduced_scope, reduced_scope.digest(), frozen_denominator=4)
    assert dec == GateDecision.FAIL
    assert any("FROZEN_DENOMINATOR_VIOLATION" in r for r in reasons)


def test_b00_scope_mutation_invalidates_approval_a03():
    """A03: Modifying approved scope fields invalidates approval."""
    scope = ScopeCompiler.compile_scope(
        tenant_id="tenant-1",
        project_id="proj-1",
        run_id="run-1",
        supported_features=["order-permission-flow"],
    )
    approved_digest = scope.digest()

    # Change a field
    mutated_scope = ScopeCompiler.compile_scope(
        tenant_id="tenant-2",  # changed tenant
        project_id="proj-1",
        run_id="run-1",
        supported_features=["order-permission-flow"],
    )
    dec, reasons = ScopeCompiler.validate_approved_scope(mutated_scope, approved_digest)
    assert dec == GateDecision.INCONCLUSIVE
    assert any("SCOPE_APPROVAL_INVALIDATED" in r for r in reasons)
