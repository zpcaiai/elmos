"""Bridge behaviour for the four evidence-and-measurement capabilities.

``artifact-evidence-protocol``, ``evidence-release-gate``,
``independent-verification-mesh`` and ``cost-eta-observability`` are the four
Skills whose entire value is refusing to state something they did not observe.
That makes their input adapters the most dangerous ones in the package: every
field the adapter could plausibly default — an input digest, a health probe, a
verifier's independence class, a token count — is a field whose invented value
would satisfy the exact check the capability exists to run.

So these tests assert three separate things, and the third is the one that
matters most:

* a complete payload reaches the kernel and comes back carrying something the
  legacy engine structurally cannot produce;
* a v2-shaped payload still works, falls through to the legacy engine, and the
  translation gap is *recorded* rather than silently absorbed;
* a payload the kernel reads and then rejects on a domain rule surfaces that
  rejection.  A bridge that downgraded a kernel ``REJECTED`` to a legacy
  ``BLOCKED`` would be worse than having no kernel at all, because the weaker
  engine would be overturning a correct answer while looking like a fallback.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from elmos_autonomy_kernel.evidence import (
    Evidence,
    EvidenceBundle,
    EvidenceKind,
    Outcome,
    digest_bytes,
    seal_bundle,
)
from elmos_autonomy_kernel.releasegate import set_default_seal_key
from elmos_repository_autonomy import kernel_bridge
from elmos_repository_autonomy.dispatcher import AutonomyRuntime
from elmos_repository_autonomy.models import Status

SEAL_KEY = b"r" * 32
AT = datetime(2026, 1, 1, tzinfo=UTC)
AT_TEXT = "2026-01-01T00:00:00.000000Z"
SNAPSHOT = "sha256:" + "a" * 64
OTHER_SNAPSHOT = "sha256:" + "c" * 64
SOURCE_DIGEST = digest_bytes(b"input-source")


@pytest.fixture()
def runtime() -> AutonomyRuntime:
    return AutonomyRuntime()


@pytest.fixture(autouse=True)
def _seal_key():
    set_default_seal_key(SEAL_KEY)
    yield
    set_default_seal_key(None)


def _fell_through(result) -> bool:
    """The bridge declined and said so, and the legacy engine answered."""

    unmapped = [item for item in result.reasons
                if item.startswith("KERNEL_INPUT_UNMAPPED:") or item == "KERNEL_NOT_APPLICABLE"]
    return bool(unmapped) and "ENGINE:legacy" in result.reasons


# --- payload builders --------------------------------------------------------


def artifact_payload(**overrides):
    payload = {
        "producer_step": {
            "stepId": "step-1",
            "producerId": "runner-a",
            "tenantId": "tenant-a",
            "environmentFingerprint": "py3.11-linux-x86_64",
            "producedAt": AT_TEXT,
            "evidenceId": "ev-1",
            "claim": "the unit suite passes",
            "kind": "test-report",
            "outcome": "PASS",
        },
        "content": {"mediaType": "text/plain", "text": "42 passed, 0 failed"},
        "repo_snapshot": {"snapshotSha": SNAPSHOT, "inputDigests": [SOURCE_DIGEST]},
        "task_spec_version": "1",
        "security_label": "internal",
    }
    payload.update(overrides)
    return payload


def _evidence(evidence_id: str, kind: EvidenceKind) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        claim=f"{evidence_id} observed",
        kind=kind,
        artifact_digests=(digest_bytes(b"junit.xml"),),
        input_digests=(SOURCE_DIGEST,),
        producer_id="runner-a",
        produced_at=AT,
        environment_fingerprint="py3.11-linux",
        outcome=Outcome.PASS,
    )


def release_payload(**overrides):
    bundle = seal_bundle(
        EvidenceBundle(
            bundle_id="bundle-1",
            repo_snapshot_sha=SNAPSHOT,
            evidence=(_evidence("ev-test", EvidenceKind.TEST_REPORT),
                      _evidence("ev-policy", EvidenceKind.POLICY_DECISION)),
            produced_at=AT,
        ),
        key=SEAL_KEY,
    )
    payload = {
        "completion_claim": {"claimant": "agent-a", "assertsComplete": True},
        "acceptance_criteria": {
            "runId": "run-1",
            "repoSnapshotSha": SNAPSHOT,
            "decidedAt": AT_TEXT,
            "mandatoryGateIds": ["gate-unit-tests", "gate-policy"],
            "policyDecision": {"decisionId": "pd-1", "decision": "ALLOW",
                               "policySnapshotHash": "sha256:" + "b" * 64},
        },
        "validation_results": {
            "gateResults": [
                {"gateId": "gate-unit-tests", "status": "PASS", "evidenceIds": ["ev-test"],
                 "requiredEvidenceKinds": ["test-report"]},
                {"gateId": "gate-policy", "status": "PASS", "evidenceIds": ["ev-policy"],
                 "requiredEvidenceKinds": ["policy-decision"]},
            ],
            "findings": [],
        },
        "artifacts": {"bundle": {"payload": bundle.payload, "seal": bundle.seal}},
        "approvals": {"waivers": []},
        "deployment_results": {
            "health": {"livez": True, "readyz": True, "metrics": True, "version": True},
            "rollbackPlan": {"planId": "rollback-1", "complete": True,
                             "steps": ["redeploy previous image"]},
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key] = {**payload[key], **value}
        else:
            payload[key] = value
    return payload


def mesh_payload(**overrides):
    payload = {
        "change_set": {
            "claim": {
                "claimId": "claim-1",
                "statement": "the patch fixes the null dereference",
                "producerId": "generator-a",
                "producerIndependenceClass": "model-family-x",
            },
            "producedAt": AT_TEXT,
        },
        "validation_dag": {
            "verdicts": [
                {"verifier": {"verifierId": "tests-a", "kind": "test",
                              "independenceClass": "ci-runner"},
                 "claimId": "claim-1", "value": "CONFIRMED", "evidenceIds": ["ev-tests"]},
                {"verifier": {"verifierId": "scan-c", "kind": "scanner",
                              "independenceClass": "scanner-vendor-z"},
                 "claimId": "claim-1", "value": "CONFIRMED", "evidenceIds": ["ev-scan"]},
                {"verifier": {"verifierId": "review-b", "kind": "model-review",
                              "independenceClass": "model-family-y"},
                 "claimId": "claim-1", "value": "REFUTED", "evidenceIds": ["ev-review"],
                 "rationale": "the regression still reproduces on aarch64"},
            ],
        },
        "task_spec": {"version": "1"},
        "repository_snapshot": {"sha256": SNAPSHOT},
        "policies": {"quorum": {"requiredVerifiers": 3, "requiredAgreement": 2,
                                "independenceClassesRequired": 2}},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key] = {**payload[key], **value}
        else:
            payload[key] = value
    return payload


def cost_payload(**overrides):
    payload = {
        "run_events": {
            "runId": "run-1", "repoSnapshotSha": SNAPSHOT,
            "completedSteps": 3, "totalSteps": 10,
            "requiredPhases": ["model", "tool", "approval"],
            "spans": [
                {"spanId": "s-model", "phase": "model", "durationMs": 1200},
                {"spanId": "s-tool", "phase": "tool", "durationMs": 300,
                 "dependsOn": ["s-model"]},
                {"spanId": "s-approval", "phase": "approval", "durationMs": 3_600_000,
                 "dependsOn": ["s-tool"]},
            ],
        },
        "historical_runs": {
            "samples": [{"sizeUnits": 100, "durationMs": 1000} for _ in range(6)],
            "durationsMs": [100, 200, 300],
            "sloTargets": {"machine-wall-clock-p50": 500},
        },
        "repo_features": {
            "repoSnapshotSha": SNAPSHOT, "sizeUnits": 200,
            "humanEquivalent": {"milliHours": 4500, "method": "story-point-regression"},
        },
        "model_tool_usage": {
            "records": [
                {"componentId": "c-model", "meterKey": "model.input", "quantity": 10000},
                {"componentId": "c-broken", "meterKey": "model.output", "quantity": None,
                 "note": "provider returned no usage block"},
            ],
            "tokensUsed": 12000, "tokenBudget": 100000,
        },
        "cache_metrics": {"hits": 8, "misses": 2, "savedTokens": 5000,
                          "meterKey": "model.input"},
        "pricing_profile": {
            "profileId": "prices-2026-01", "version": "3", "currency": "USD",
            "prices": [{"meterKey": "model.input", "price": "3", "perUnits": 1000},
                       {"meterKey": "model.output", "price": "15", "perUnits": 1000}],
        },
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(payload.get(key), dict):
            payload[key] = {**payload[key], **value}
        else:
            payload[key] = value
    return payload


# --- a complete payload reaches the kernel -----------------------------------


def test_artifact_evidence_reaches_the_kernel_bound_to_its_input_digests(runtime):
    """The kernel's evidence names the inputs it was produced from; legacy's cannot."""

    result = runtime.execute("artifact-evidence-protocol", artifact_payload())

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    assert result.output["evidence"]["inputDigests"] == [SOURCE_DIGEST]
    assert result.output["provenance_edge"]["fromDigests"] == [SOURCE_DIGEST]
    # The binding digest is over (artifact, inputs, producer, environment): change
    # any one of them and the evidence no longer verifies for that claim.
    assert result.output["integrity_record"]["bindingDigest"].startswith("sha256:")


def test_release_gate_uses_the_kernel_reasoning_under_the_legacy_p05_ceiling(runtime):
    """The kernel decides; CertificationEngine still owns the attestation.

    Routing this skill to the kernel buys strictly better *blocking* - NOT_RUN
    and SKIPPED are non-verdicts, the rollback plan must be complete, waivers
    expire.  It must not also buy the right to issue P05: in this package
    P05_DEPLOYMENT_COMPLETE is issued only by ``CertificationEngine``, which
    binds signed evidence and persisted customer acceptance to the candidate
    digest, whereas the kernel's own bundle seal uses a process-local key.

    Letting the deeper engine attest would have narrowed a package-wide
    invariant to "holds for legacy-shaped payloads only", which is how a safety
    property quietly becomes a default.  So the bridge caps the attestation and
    records why, and the kernel's reasoning is preserved verbatim underneath.
    """

    result = runtime.execute("evidence-release-gate", release_payload())

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons

    attestation = result.output["deployment_complete_attestation"]
    assert attestation["attested"] is False
    assert attestation["gate"] == "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED"
    assert attestation["kernelAttested"] is True
    assert attestation["requiredNext"] == "trusted-certification-engine"
    assert "process-local" in attestation["withheldReason"]

    # Everything the kernel actually decided survives the cap.
    assert result.output["acceptance_decision"]["justifyingEvidenceIds"] == [
        "ev-policy", "ev-test"
    ]
    assert attestation["decisionDigest"].startswith("sha256:")


def test_the_p05_ceiling_holds_on_both_engines(runtime):
    """No payload shape reaches an attested P05 through the dispatcher.

    The legacy gate hard-codes NOT_ISSUED and the kernel path is capped, so the
    invariant is a property of the dispatcher rather than of whichever engine
    happened to answer - which is the only form in which it is worth having.
    """

    for payload in (release_payload(), {"completion_claim": {"status": "PASS"},
                                        "acceptance_criteria": [{"id": "c1"}],
                                        "validation_results": [{"status": "PASS"}]}):
        result = runtime.execute("evidence-release-gate", payload)
        attestation = result.output.get("deployment_complete_attestation", {})
        assert attestation.get("attested") is not True, result.reasons


def test_verification_mesh_reaches_the_kernel_and_preserves_dissent(runtime):
    """The minority verdict survives the consensus rather than being averaged into it.

    Two independent confirmations carry the quorum, so the mesh answers
    CONFIRMED - and the reviewer who refuted the claim is still in the result,
    with its rationale, because the minority verdict is the one an incident
    review goes looking for.  The legacy engine has nowhere to put it.
    """

    result = runtime.execute("independent-verification-mesh", mesh_payload())

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    adjudication = result.output["verification_run"]["adjudication"]
    assert adjudication["consensus"] == "CONFIRMED"
    dissent = adjudication["dissent"]
    assert [item["verifier"]["verifierId"] for item in dissent] == ["review-b"]
    assert dissent[0]["rationale"] == "the regression still reproduces on aarch64"


def test_cost_eta_reaches_the_kernel_and_reports_an_unmeasured_cost_as_null(runtime):
    """A provider that returned no usage yields ``null``/``measured: false``, not 0."""

    result = runtime.execute("cost-eta-observability", cost_payload())

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    assert result.status is Status.PARTIAL
    breakdown = result.output["cost_breakdown"]
    components = {item["componentId"]: item for item in breakdown["components"]}
    assert components["c-broken"]["cost"] is None
    assert components["c-broken"]["measured"] is False
    assert breakdown["total"] is None
    assert result.output["billing_record"]["amount"] is None
    assert result.output["billing_record"]["final"] is False


# --- a v2-shaped payload still works, and the gap is recorded ----------------


def test_legacy_artifact_payload_falls_through_with_the_gap_recorded(runtime):
    """No input digests means no binding to derive, so the legacy engine answers."""

    result = runtime.execute(
        "artifact-evidence-protocol",
        {"producer_step": {"id": "step"}, "content": {"ok": True},
         "repo_snapshot": "sha256:legacy"},
    )

    assert result.error is None
    assert _fell_through(result)
    assert result.output["artifact"]["content_hash"].startswith("sha256:")


def test_legacy_release_payload_falls_through_with_the_gap_recorded(runtime):
    """A list of artifact hashes is not a sealed bundle, and cannot be turned into one."""

    result = runtime.execute(
        "evidence-release-gate",
        {"completion_claim": {"status": "SUCCEEDED"},
         "acceptance_criteria": [{"id": "build"}],
         "validation_results": [{"id": "build", "status": "PASS"}],
         "artifacts": [{"content_hash": "sha256:" + "d" * 64}],
         "approvals": [{"status": "APPROVED"}],
         "deployment_results": {"rollback_ready": True}},
    )

    assert result.error is None
    assert _fell_through(result)
    assert result.output["gate_results"] == [
        {"id": "build", "status": "PASS", "evidence_ids": []}
    ]


def test_legacy_mesh_payload_falls_through_with_the_gap_recorded(runtime):
    """Status rows carry no verifier, so independence cannot be checked or invented."""

    result = runtime.execute(
        "independent-verification-mesh",
        {"change_set": ["src/app.py"],
         "validation_dag": [{"id": "build", "status": "PASS"}],
         "task_spec": {"acceptance_criteria": [{"id": "build"}]},
         "repository_snapshot": {"sha256": SNAPSHOT},
         "policies": []},
    )

    assert result.error is None
    assert _fell_through(result)
    assert result.output["verification_run"]["validator_count"] == 1


def test_legacy_cost_payload_falls_through_with_the_gap_recorded(runtime):
    """A flat event list has no run id, no sizing and no price list to derive from."""

    result = runtime.execute(
        "cost-eta-observability",
        {"run_events": [{"wall_clock_ms": 10, "status": "PASS"}],
         "repo_features": {}, "cache_metrics": {}, "pricing_profile": {}},
    )

    assert result.error is None
    assert _fell_through(result)
    assert result.output["progress_snapshot"]["events"] == 1


def test_a_decode_level_kernel_rejection_falls_through_rather_than_failing(runtime):
    """A shape the kernel cannot read is this module's gap, not the caller's error."""

    payload = mesh_payload()
    payload["validation_dag"]["verdicts"][0]["value"] = "PROBABLY"

    result = runtime.execute("independent-verification-mesh", payload)

    assert result.error is None
    assert "KERNEL_INPUT_UNMAPPED:MALFORMED_INPUT" in result.reasons
    assert "ENGINE:legacy" in result.reasons


# --- a domain rejection is never downgraded ---------------------------------


def test_a_kernel_domain_rejection_is_not_downgraded_to_a_legacy_success(runtime):
    """The bridge's single most important safety property.

    The payload is complete: the kernel reads every field and then rejects the
    release because a mandatory gate never ran.  If the bridge treated that as a
    fallback condition, the legacy gate would answer instead — and the legacy
    gate would happily report ``BLOCKED`` with ``release_bundle`` and
    ``gate_results`` attached, which reads to a caller as "the pipeline is
    working" rather than "a mandatory check never executed".
    """

    payload = release_payload(validation_results={
        "gateResults": [
            {"gateId": "gate-unit-tests", "status": "NOT_RUN"},
            {"gateId": "gate-policy", "status": "PASS", "evidenceIds": ["ev-policy"],
             "requiredEvidenceKinds": ["policy-decision"]},
        ],
        "findings": [],
    })

    result = runtime.execute("evidence-release-gate", payload)

    assert result.error is not None
    assert result.error.code == "ACCEPTANCE_REJECTED"
    assert result.error.details["engine"] == "kernel"
    assert "GATE_NOT_RUN" in result.error.details["message"]
    # No legacy answer was substituted for the rejection.
    assert result.output == {}
    assert "ENGINE:legacy" not in result.reasons
    assert "ENGINE:kernel" not in result.reasons


def test_a_stale_snapshot_rejection_is_not_downgraded_either(runtime):
    """Sizing a run from another snapshot's features is refused, not fallen back from."""

    result = runtime.execute(
        "cost-eta-observability",
        cost_payload(repo_features={"repoSnapshotSha": OTHER_SNAPSHOT}),
    )

    assert result.error is not None
    assert result.error.code == "STALE_SNAPSHOT"
    assert result.output == {}
    assert "ENGINE:legacy" not in result.reasons


def test_an_unbound_seal_key_fails_closed_instead_of_falling_back(runtime):
    """A deployment that never bound the seal key gets an error, not a softer answer.

    This is the operational cost of routing the release gate to the kernel, and
    it is the right cost.  The gate's entire job is to check a signature; with no
    key bound it cannot, and answering from the legacy engine instead would turn
    "we cannot verify this bundle" into a routine BLOCKED that looks like every
    other pipeline hold.  Note that a v2-shaped payload is unaffected - it never
    reaches the kernel in the first place.
    """

    set_default_seal_key(None)
    result = runtime.execute("evidence-release-gate", release_payload())

    assert result.error is not None
    assert result.error.code == "EVIDENCE_UNVERIFIABLE"
    assert result.output == {}
    assert "ENGINE:legacy" not in result.reasons


# --- the silent-zero test ----------------------------------------------------


def test_routing_cost_eta_through_the_bridge_cannot_manufacture_a_zero(runtime):
    """A failed measurement stays a failed measurement on both sides of the bridge.

    Three doors are checked, because the defect this repository shipped three
    times got in through a different one each time:

    1. the kernel path reports the unmeasured component as ``null`` with
       ``measured: false`` and refuses to publish a total;
    2. the adapter will not invent the pricing profile, the run identity or the
       repository sizing that would let an unpriced run be priced at zero — it
       returns ``{}`` and the call is recorded as unmapped;
    3. the legacy path, which *does* fall back to zero, now labels every zero it
       produced, so no reader can mistake an unmeasured 0 for a measured one.
    """

    kernel_side = runtime.execute("cost-eta-observability", cost_payload())
    assert "ENGINE:kernel" in kernel_side.reasons
    assert kernel_side.output["billing_record"]["amount"] is None
    assert kernel_side.output["billing_record"]["measuredSubtotal"] is not None

    # 2. No price list: the adapter refuses rather than pricing the run at zero.
    unpriced = cost_payload()
    unpriced.pop("pricing_profile")
    assert kernel_bridge.serve("cost-eta-observability", unpriced).served is False

    # 3. The legacy fallback's zeros are labelled.
    legacy = runtime.execute(
        "cost-eta-observability",
        {"run_events": [], "repo_features": {}, "cache_metrics": {}, "pricing_profile": {},
         "model_tool_usage": [{"category": "model"}]},
    )
    assert _fell_through(legacy)
    assert legacy.output["progress_snapshot"]["machine_wall_clock_seconds"] == 0
    assert legacy.output["progress_snapshot"]["machine_wall_clock_measured"] is False
    assert legacy.output["eta_distribution"]["p50"] == 0
    assert legacy.output["eta_distribution"]["measured"] is False
    assert legacy.output["billing_record"]["total"] == "0"
    assert legacy.output["billing_record"]["measured"] is False
    assert legacy.output["billing_record"]["unmeasured_components"] == ["model"]
    assert legacy.output["cost_breakdown"][0]["measured"] is False
    assert legacy.output["slo_metrics"]["cache_hit_rate"] == 0
    assert legacy.output["slo_metrics"]["cache_hit_rate_measured"] is False


# --- the honesty stamps on the legacy engine ---------------------------------


def test_legacy_artifact_evidence_says_it_is_bound_to_nothing(runtime):
    """``integrity_record`` reads as provenance; it is a content address only."""

    result = runtime.execute(
        "artifact-evidence-protocol",
        {"producer_step": {"id": "step"}, "content": {"ok": True}},
    )

    record = result.output["integrity_record"]
    assert record["input_digests_bound"] is False
    assert record["binding"] == "content-address-only"
    assert "not bound to the input digests" in record["method_note"]


def test_legacy_verification_mesh_says_the_verdict_is_unreplicated(runtime):
    """A PASS from self-reported rows is not a verified claim, and now says so."""

    result = runtime.execute(
        "independent-verification-mesh",
        {"change_set": [], "validation_dag": [{"id": "build", "status": "PASS"}],
         "task_spec": {"acceptance_criteria": [{"id": "build"}]},
         "repository_snapshot": {"sha256": SNAPSHOT}, "policies": []},
    )

    recommendation = result.output["release_recommendation"]
    assert recommendation["status"] == "PASS"
    assert recommendation["verdict_replication"] == "UNREPLICATED"
    assert recommendation["independence_checked"] is False
    assert recommendation["dissent_preserved"] is False
    coverage = result.output["coverage_report"]
    assert coverage["independence_checked"] is False
    # True only because there were no P0/P1 findings to be independent about.
    assert coverage["high_severity_independent"] is True
    assert coverage["high_severity_independent_vacuous"] is True


def test_legacy_release_gate_names_the_gates_that_never_ran(runtime):
    """``reasons`` alone cannot tell a failed gate from a gate that never ran."""

    result = runtime.execute(
        "evidence-release-gate",
        {"acceptance_criteria": [{"id": "build"}, {"id": "security"}],
         "validation_results": [{"id": "build", "status": "PASS"},
                                {"id": "security", "status": "SKIPPED"}],
         "artifacts": [], "approvals": [], "deployment_results": {}},
    )

    decision = result.output["acceptance_decision"]
    assert decision["unobserved_gates"] == ["security"]
    assert decision["gate_statuses"] == {"build": "PASS", "security": "SKIPPED"}
    # No artifacts were supplied, so "artifact-integrity" is absent from reasons
    # because nothing was checked - not because integrity was established.
    assert decision["artifact_integrity_checked"] is False
    assert "artifact-integrity" not in decision["reasons"]


def test_legacy_cost_eta_labels_every_zero_it_substituted(runtime):
    """An accurate measurement is left unstamped; only the substituted zeros are marked."""

    result = runtime.execute(
        "cost-eta-observability",
        {"run_events": [{"wall_clock_ms": 10, "status": "PASS"},
                        {"phase": "build", "status": "PASS"}],
         "repo_features": {}, "cache_metrics": {"hit_rate": 0.5}, "pricing_profile": {},
         "model_tool_usage": [{"category": "model", "quantity": 2, "unit_price": "3"}]},
    )

    progress = result.output["progress_snapshot"]
    assert progress["unmeasured_event_count"] == 1
    assert progress["machine_wall_clock_measured"] is False
    assert result.output["billing_record"]["measured"] is True
    assert result.output["billing_record"]["total"] == "6"
    assert result.output["slo_metrics"]["cache_hit_rate_measured"] is True
