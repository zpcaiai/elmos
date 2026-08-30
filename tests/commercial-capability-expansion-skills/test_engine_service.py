"""Fail-closed service and exact kernel-surface tests."""

# ruff: noqa: E402 -- the repository-local engine source is injected for integration tests.

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = ROOT / "engines/commercial-capability-expansion-engine/src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from elmos_commercial_expansion.service import (
    CommercialCapabilityExpansionService,
    get_commercial_status,
    list_capability_kernels,
)


def test_kernel_public_surface_is_read_only_and_registry_is_private():
    import elmos_commercial_expansion.kernels as kernels

    assert not hasattr(kernels, "EXACT_SKILL_HANDLERS")
    assert not hasattr(kernels, "EXACT_SKILL_INPUT_CONTRACTS")
    assert not hasattr(kernels, "BuildExecutionKernel")
    assert not hasattr(kernels, "DatabaseDataKernel")
    assert not hasattr(kernels, "VerificationKernel")


def test_status_is_bounded_and_never_claims_external_readiness():
    status = get_commercial_status()
    assert status["skills_count"] == 85
    assert status["kernels_count"] == 8
    assert status["status"] in {"NOT_READY", "LOCAL_BOUNDED_UNQUALIFIED"}
    assert status["status"] != "ACTIVE"
    assert status["exact_registry"] is True
    assert status["external_provider_status"] == "NOT_RUN"
    assert status["native_runtime_status"] == "NOT_RUN"
    assert status["independent_verification_status"] == "NOT_RUN"
    assert status["certification_status"] == "NOT_CERTIFIED"
    assert status["production_readiness_status"] == "NOT_READY"
    assert set(status["operational_controls"].values()) == {
        "NOT_CONFIGURED",
        "NOT_RUN",
    }


def test_kernel_inventory_has_exact_manifest_counts_and_no_certification_claim():
    kernels = list_capability_kernels()
    assert [item["exact_handler_count"] for item in kernels] == [10, 10, 10, 9, 14, 10, 10, 12]
    assert all(item["exact_registry_complete"] for item in kernels)
    assert all(item["status"] in {"NOT_READY", "LOCAL_BOUNDED_UNQUALIFIED"} for item in kernels)
    assert all(item["external_evidence_status"] == "NOT_RUN" for item in kernels)
    assert all(item["certification_status"] == "NOT_CERTIFIED" for item in kernels)


def test_legacy_workflow_entrypoint_fails_closed_without_signed_exact_invocation():
    result = CommercialCapabilityExpansionService().run_commercial_workflow(
        target_files=["src/auth.py"], change_intent="unsafe legacy call"
    )
    assert result == {
        "status": "NOT_RUN",
        "outcome": "BLOCKED",
        "reason": "SIGNED_EXACT_INVOCATION_REQUIRED",
        "external_provider_status": "NOT_RUN",
        "native_runtime_status": "NOT_RUN",
        "independent_verification_status": "NOT_RUN",
        "certification_status": "NOT_CERTIFIED",
    }
