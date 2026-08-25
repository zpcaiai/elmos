"""Behavioural contract for the durable cache SLO control plane.

``slo_service`` is the only place where a tuning proposal becomes something the
cache actually serves, so every assertion here is about *durable* state: what
survives a reopen, what a second writer is allowed to observe, and what a
foreign tenant can learn. Nothing under test is mocked -- a real SQLite store, a
real content-addressable store and real Ed25519 signatures are used throughout,
because the failure modes worth catching (a chain that forks, a candidate that
resurrects itself, an error that leaks existence) only exist at that layer.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import pytest

from elmos_build_cache.canonical import digest_of, sha256_bytes
from elmos_build_cache.cas import ContentAddressableStore
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.db import SqliteMetadataStore
from elmos_build_cache.db import store as store_module
from elmos_build_cache.enums import ArtifactStorageState
from elmos_build_cache.errors import (
    ConflictError,
    ContractViolation,
    ErrorCode,
    IdempotencyConflict,
    NotFound,
    PermissionDenied,
    ProvenanceInvalid,
)
from elmos_build_cache.parity import (
    MANDATORY_SCENARIOS,
    EvidenceBinding,
    ParityReport,
    ParityThresholds,
    ScenarioResult,
    ScenarioStatus,
    evaluate_parity,
)
from elmos_build_cache.security import (
    Ed25519ProvenanceSigner,
    HmacProvenanceSigner,
    SignedStatement,
)
from elmos_build_cache.slo_autotune import (
    ROLLOUT_ORDER,
    CacheTuningParameters,
    RollbackReason,
    RolloutEvidence,
    RolloutPhase,
    RolloutState,
    TuningObservation,
    TuningProposal,
)
from elmos_build_cache.slo_service import (
    SLO_APPROVAL_KIND,
    SLO_OBSERVATION_ATTESTATION_KIND,
    SLO_ROLLOUT_EVIDENCE_ATTESTATION_KIND,
    CacheSloControlService,
    CacheSloRuntimeRegistry,
    SloEvidenceState,
    StaticSloApprovalResolver,
    slo_approval_statement,
    slo_observation_artifact,
    slo_observation_statement,
    slo_rollout_evidence_artifact,
    slo_rollout_evidence_statement,
    slo_scope_digest,
)

CONTROL_EVENTS_TABLE = "cache_slo_control_events_v12"
SLO_SQLITE_MIGRATION = "0007_slo_control.sql"
SLO_POSTGRES_MIGRATION = "0009_slo_control.sql"

TENANT = "tenant-slo"
PROJECT = "project-slo"
CONTROLLER = "controller-slo"
OTHER_TENANT = "tenant-other"
OTHER_PROJECT = "project-other"

COLLECTOR = "slo-collector"
OBSERVATION_VERIFIER = "slo-observation-verifier"
EXECUTOR = "slo-executor"
PARITY_VERIFIER = "slo-parity-verifier"
APPROVER = "slo-operator"


def _principal(label: str) -> str:
    return sha256_bytes(label.encode())


def _baseline() -> CacheTuningParameters:
    return CacheTuningParameters(capacity_bytes=10 * 1024 * 1024 * 1024)


def _observation(**overrides: Any) -> TuningObservation:
    values: dict[str, Any] = {
        "sample_count": 10_000,
        "unexpected_prefix_miss_rate": 0.03,
        "wrong_shard_rate": 0.02,
        "environment_hit_rate": 0.90,
        "storage_pressure": 0.50,
        "useful_prefetch_rate": 0.10,
        "context_limit_pressure": 0.80,
        "restore_bypass_rate": 0.40,
    }
    values.update(overrides)
    return TuningObservation(**values)


def _rollout_state(status: dict[str, Any]) -> RolloutState:
    """Rebuild the durable rollout state from the public status document."""

    state = status["state"]
    reason = state["rollback_reason"]
    return RolloutState(
        baseline_digest=str(state["baseline_digest"]),
        candidate_digest=(
            None if state["candidate_digest"] is None else str(state["candidate_digest"])
        ),
        serving_digest=str(state["serving_digest"]),
        phase=RolloutPhase(str(state["phase"])),
        consecutive_passes=int(state["consecutive_passes"]),
        epoch=int(state["epoch"]),
        rollback_reason=None if reason is None else RollbackReason(str(reason)),
    )


def _proposal_of(document: dict[str, Any]) -> TuningProposal:
    """Rebuild the exact proposal the service persisted, from its own bytes."""

    return TuningProposal(
        baseline_digest=str(document["baseline_digest"]),
        candidate=CacheTuningParameters(**dict(document["candidate"])),
        reason_codes=tuple(str(code) for code in document["reason_codes"]),
        shadow_only=True,
    )


@dataclass
class _Value:
    """A source the control plane pulls from; the plane cannot write to it."""

    value: Any = None

    def current(
        self,
        tenant_id: str,
        project_id: str,
        controller_id: str,
        principal_digest: str,
    ) -> Any:
        if self.value is None:
            raise AssertionError("the test did not stage a value for this source")
        return self.value


@dataclass
class Harness:
    """One tenant's SLO control plane, wired to real storage and real keys."""

    root: Path
    clock: ManualClock
    cas: ContentAddressableStore
    tenant_id: str = TENANT
    project_id: str = PROJECT
    controller_id: str = CONTROLLER
    principal_digest: str = field(default_factory=lambda: _principal("principal-a"))
    baseline: CacheTuningParameters = field(default_factory=_baseline)
    observation_signer: Ed25519ProvenanceSigner = field(
        default_factory=lambda: Ed25519ProvenanceSigner.generate("observation-key")
    )
    evidence_signer: Ed25519ProvenanceSigner = field(
        default_factory=lambda: Ed25519ProvenanceSigner.generate("evidence-key")
    )
    approval_signer: Ed25519ProvenanceSigner = field(
        default_factory=lambda: Ed25519ProvenanceSigner.generate("approval-key")
    )
    resolver: StaticSloApprovalResolver = field(default_factory=StaticSloApprovalResolver)
    observations: _Value = field(default_factory=_Value)
    windows: _Value = field(default_factory=_Value)

    # -- storage ----------------------------------------------------------
    @property
    def database(self) -> Path:
        return self.root / "index.sqlite"

    def open_store(self) -> SqliteMetadataStore:
        return SqliteMetadataStore.open(self.database, self.clock)

    def register(self, store: SqliteMetadataStore, document: Any, kind: str) -> str:
        """Publish one signed envelope the way its own plane would."""

        digest = self.cas.put_document(document, artifact_kind=kind)
        info = self.cas.info(digest)
        with store.transaction():
            store.register_artifact(
                self.tenant_id, digest, info.size, "application/json", kind
            )
        return digest

    def service(
        self, store: SqliteMetadataStore, **overrides: Any
    ) -> CacheSloControlService:
        kwargs: dict[str, Any] = {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "controller_id": self.controller_id,
            "principal_digest": self.principal_digest,
            "baseline": self.baseline,
            "store": store,
            "cas": self.cas,
            "observation_source": self.observations,
            "evidence_source": self.windows,
            "approval_resolver": self.resolver,
            "observation_verifier": self.observation_signer,
            "evidence_verifier": self.evidence_signer,
            "approval_verifier": self.approval_signer,
            "clock": self.clock,
            "minimum_samples": 1_000,
            "required_windows": 2,
        }
        kwargs.update(overrides)
        return CacheSloControlService(**kwargs)

    # -- signed inputs ----------------------------------------------------
    def stage_observation(
        self,
        store: SqliteMetadataStore,
        observation: TuningObservation | None = None,
        *,
        collector: str = COLLECTOR,
        verifier: str = OBSERVATION_VERIFIER,
        issued_at: float | None = None,
        expires_at: float | None = None,
        signer: Ed25519ProvenanceSigner | None = None,
    ) -> Any:
        from elmos_build_cache.slo_service import TrustedTuningObservation

        measured = observation or _observation()
        statement = slo_observation_statement(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            baseline_digest=self.baseline.digest,
            observation=measured,
            collector_identity=collector,
            verifier_identity=verifier,
            issued_at=self.clock.now() - 10 if issued_at is None else issued_at,
            expires_at=self.clock.now() + 3_600 if expires_at is None else expires_at,
        )
        attestation = (signer or self.observation_signer).sign_statement(
            SLO_OBSERVATION_ATTESTATION_KIND, statement
        )
        envelope = slo_observation_artifact(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            baseline_digest=self.baseline.digest,
            observation=measured,
            collector_identity=collector,
            verifier_identity=verifier,
            attestation=attestation,
        )
        digest = self.register(store, envelope, "cache-slo-observation")
        trusted = TrustedTuningObservation(
            measured, digest, attestation, collector, verifier
        )
        self.observations.value = trusted
        return trusted

    def approve(
        self,
        store: SqliteMetadataStore,
        document: dict[str, Any],
        *,
        maximum_phase: RolloutPhase = RolloutPhase.FULL,
        approver: str = APPROVER,
        issued_at: float | None = None,
        expires_at: float | None = None,
        signer: Ed25519ProvenanceSigner | None = None,
        register: bool = True,
    ) -> tuple[SignedStatement, str]:
        proposal = _proposal_of(document)
        statement = slo_approval_statement(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal=proposal,
            approver_identity=approver,
            maximum_phase=maximum_phase,
            issued_at=self.clock.now() - 10 if issued_at is None else issued_at,
            expires_at=self.clock.now() + 3_600 if expires_at is None else expires_at,
        )
        receipt = (signer or self.approval_signer).sign_statement(
            SLO_APPROVAL_KIND, statement
        )
        if register:
            self.register(store, receipt.to_dict(), "cache-slo-approval")
        self.resolver.register(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal_digest=proposal.proposal_digest,
            receipt=receipt,
        )
        return receipt, digest_of(receipt.to_dict())

    def parity_report(
        self,
        *,
        report_id: str,
        approval_digest: str,
        configuration_digest: str,
        executor: str = EXECUTOR,
        verifier: str = PARITY_VERIFIER,
        authenticated: bool = True,
        metrics_override: dict[str, float | int] | None = None,
        scenario_status: ScenarioStatus = ScenarioStatus.PASS,
    ) -> ParityReport:
        metrics: dict[str, float | int] = dict(asdict(ParityThresholds()))
        if metrics_override:
            metrics.update(metrics_override)
        scenarios = [
            ScenarioResult(
                name, scenario_status, (sha256_bytes(f"evidence:{name}".encode()),)
            )
            for name in MANDATORY_SCENARIOS
        ]
        binding = EvidenceBinding(
            sha256_bytes(b"source"),
            configuration_digest,
            sha256_bytes(b"providers"),
            sha256_bytes(b"corpus"),
            sha256_bytes(b"platform"),
            "2026-08-20T12:00:00Z",
            executor,
            verifier,
            tenant_scope_digest=self.scope_digest if authenticated else None,
            authorization_digest=approval_digest if authenticated else None,
        )
        return evaluate_parity(
            report_id=report_id,
            metrics=metrics,
            cohorts={"representative": metrics},
            scenarios=scenarios,
            binding=binding,
        )

    @property
    def scope_digest(self) -> str:
        return slo_scope_digest(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
        )

    def stage_window(
        self,
        store: SqliteMetadataStore,
        *,
        document: dict[str, Any],
        approval_digest: str,
        status: dict[str, Any],
        evidence_state: SloEvidenceState = SloEvidenceState.EXTERNAL_VERIFIED,
        report: ParityReport | None = None,
        report_id: str = "parity-report",
        executor: str = EXECUTOR,
        verifier: str = PARITY_VERIFIER,
        issued_at: float | None = None,
        expires_at: float | None = None,
        signer: Ed25519ProvenanceSigner | None = None,
        **evidence_overrides: Any,
    ) -> Any:
        from elmos_build_cache.slo_service import TrustedRolloutWindow

        parity = report or self.parity_report(
            report_id=report_id,
            approval_digest=approval_digest,
            configuration_digest=str(document["candidate_digest"]),
            executor=executor,
            verifier=verifier,
        )
        values: dict[str, Any] = {
            "parity_report": parity,
            "provider_accounting_matches": True,
            "worst_cohort_regressed": False,
            "unknown_outcome_rate": 0.0,
            "unknown_outcome_budget": 0.01,
            "out_of_distribution": False,
            "cost_guardrail_passed": True,
            "clean_fallback_exercised": True,
            "rollback_exercised": True,
        }
        values.update(evidence_overrides)
        evidence = RolloutEvidence(**values)
        proposal = _proposal_of(document)
        current = _rollout_state(status)
        head = str(status["event_digest"])
        statement = slo_rollout_evidence_statement(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal=proposal,
            approval_digest=approval_digest,
            current_state=current,
            head_event_digest=head,
            evidence=evidence,
            evidence_state=evidence_state,
            executor_identity=executor,
            verifier_identity=verifier,
            issued_at=self.clock.now() - 10 if issued_at is None else issued_at,
            expires_at=self.clock.now() + 3_600 if expires_at is None else expires_at,
        )
        attestation = (signer or self.evidence_signer).sign_statement(
            SLO_ROLLOUT_EVIDENCE_ATTESTATION_KIND, statement
        )
        envelope = slo_rollout_evidence_artifact(
            tenant_id=self.tenant_id,
            project_id=self.project_id,
            controller_id=self.controller_id,
            principal_digest=self.principal_digest,
            proposal=proposal,
            approval_digest=approval_digest,
            current_state=current,
            head_event_digest=head,
            evidence=evidence,
            evidence_state=evidence_state,
            executor_identity=executor,
            verifier_identity=verifier,
            attestation=attestation,
        )
        digest = self.register(store, envelope, "cache-slo-rollout-evidence")
        window = TrustedRolloutWindow(
            evidence, digest, evidence_state, attestation, executor, verifier
        )
        self.windows.value = window
        return window


@pytest.fixture
def harness(tmp_path: Path, clock: ManualClock) -> Harness:
    built = Harness(
        root=tmp_path / "slo", clock=clock, cas=ContentAddressableStore(tmp_path / "cas")
    )
    built.root.mkdir(parents=True, exist_ok=True)
    store = built.open_store()
    try:
        with store.transaction():
            store.ensure_project(built.tenant_id, built.project_id)
    finally:
        store.close()
    return built


@pytest.fixture
def store(harness: Harness) -> Iterator[SqliteMetadataStore]:
    opened = harness.open_store()
    yield opened
    opened.close()


@pytest.fixture
def service(harness: Harness, store: SqliteMetadataStore) -> CacheSloControlService:
    return harness.service(store)


def _installed(
    harness: Harness, store: SqliteMetadataStore, service: CacheSloControlService
) -> tuple[dict[str, Any], str]:
    """Drive the plane to an installed, shadow-phase candidate."""

    harness.stage_observation(store)
    document = service.propose()
    _, approval_digest = harness.approve(store, document)
    service.install(str(document["proposal_digest"]))
    return document, approval_digest


# ==========================================================================
# 1. state-machine transitions
# ==========================================================================
def test_a_new_controller_initializes_serving_the_baseline_and_nothing_else(
    service: CacheSloControlService, harness: Harness
) -> None:
    status = service.status()
    assert status["sequence"] == 1
    assert status["last_action"] == "INITIALIZED"
    assert status["external_evidence_state"] == "NOT_RUN"
    assert status["certified"] is False
    state = _rollout_state(status)
    assert state.phase is RolloutPhase.OBSERVE
    assert state.candidate_digest is None
    assert state.serving_digest == harness.baseline.digest
    assert state.epoch == 1
    assert status["proposal_digest"] is None
    assert status["approval_digest"] is None
    assert status["evidence_digest"] is None


def test_propose_binds_the_candidate_to_the_signed_observation_it_measured(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    trusted = harness.stage_observation(store)
    document = service.propose()

    assert document["shadow_only"] is True
    assert document["baseline_digest"] == harness.baseline.digest
    assert document["observation_artifact_digest"] == trusted.artifact_digest
    assert document["observation_digest"] == digest_of(asdict(trusted.observation))
    assert document["candidate_digest"] != harness.baseline.digest
    assert "INCREASE_LOCALITY_WEIGHT" in document["reason_codes"]

    # Proposing does not touch the serving plane at all.
    assert service.status()["sequence"] == 1
    assert service.status()["last_action"] == "INITIALIZED"

    # The proposal is durably content-addressed and owned by this tenant.
    record = store.get_artifact(harness.tenant_id, str(document["artifact_digest"]))
    assert record is not None
    assert record.artifact_kind == "cache-slo-proposal"
    assert record.storage_state is ArtifactStorageState.LOCAL


def test_repeating_an_identical_proposal_is_idempotent_not_a_conflict(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    """A replayed collector observation must not poison the proposal identity.

    ``propose`` links dependency edges alongside the proposal itself; if those
    edges shared the proposal's semantic-identity key the second, byte-identical
    call would look like a colliding identity and be refused.
    """

    harness.stage_observation(store)
    first = service.propose()
    second = service.propose()
    assert first == second


def test_a_proposals_identity_key_resolves_to_exactly_one_digest(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    """Regression: dependency edges must not pollute the identity key.

    ``MetadataStore.artifact_targets`` is not ref-kind aware, so every edge
    written under ``(source_kind, source_id)`` is returned by the lookup that
    resolves a proposal. Writing the observation and candidate-configuration
    edges under that same key made the identity resolve to three digests, and
    ``_proposal`` -- which requires exactly one -- rejected every proposal the
    service had just produced, making ``install`` and the whole rollout state
    machine unreachable.
    """

    trusted = harness.stage_observation(store)
    document = service.propose()
    identity = f"{harness.project_id}:{harness.controller_id}:{document['proposal_digest']}"

    targets = store.artifact_targets(harness.tenant_id, "cache-slo-proposal", identity)
    assert targets == [str(document["artifact_digest"])]

    # The dependency graph is still recorded, just not on the identity key.
    dependencies = store.artifact_targets(
        harness.tenant_id, "cache-slo-proposal-dependency", identity
    )
    assert trusted.artifact_digest in dependencies
    assert len(dependencies) == 2
    referrers = dict(
        (source_id, ref_kind)
        for _kind, source_id, ref_kind in store.artifact_referrers(
            harness.tenant_id, trusted.artifact_digest
        )
    )
    assert referrers.get(identity) == "observation"

    # And the proposal really is resolvable end to end.
    harness.approve(store, document)
    assert service.install(str(document["proposal_digest"]))["sequence"] == 2


def test_install_moves_an_approved_candidate_into_shadow_without_serving_it(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    status = service.status()

    assert status["sequence"] == 2
    assert status["last_action"] == "CANDIDATE_INSTALLED"
    assert status["proposal_digest"] == document["proposal_digest"]
    assert status["approval_digest"] == approval_digest
    state = _rollout_state(status)
    assert state.phase is RolloutPhase.SHADOW
    assert state.candidate_digest == document["candidate_digest"]
    # Shadow is the whole point: the candidate is installed but not served.
    assert state.serving_digest == harness.baseline.digest
    assert state.epoch == 2
    assert state.consecutive_passes == 0


def test_installing_the_same_candidate_again_is_a_no_op(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, _ = _installed(harness, store, service)
    before = service.status()
    again = service.install(str(document["proposal_digest"]))
    assert again == before
    assert service.status()["sequence"] == 2


def test_external_windows_walk_every_phase_and_only_then_serve_the_candidate(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    """The full legal lifecycle, one signed external window at a time."""

    document, approval_digest = _installed(harness, store, service)
    observed_phases: list[RolloutPhase] = [_rollout_state(service.status()).phase]
    actions: list[str] = []
    serving_before_internal: set[str] = set()

    for index in range(64):
        status = service.status()
        state = _rollout_state(status)
        if state.phase is RolloutPhase.FULL:
            break
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=status,
            report_id=f"parity-report-{index}",
        )
        status = service.advance()
        actions.append(str(status["last_action"]))
        state = _rollout_state(status)
        if state.phase in {RolloutPhase.OBSERVE, RolloutPhase.SHADOW}:
            serving_before_internal.add(state.serving_digest)
        if state.phase is not observed_phases[-1]:
            observed_phases.append(state.phase)

    assert observed_phases == list(ROLLOUT_ORDER[ROLLOUT_ORDER.index(RolloutPhase.SHADOW) :])
    assert set(actions) == {"EXTERNAL_WINDOW_ACCEPTED", "ROLLOUT_ADVANCED"}
    # Nothing was served from the candidate while the rollout was still shadow.
    assert serving_before_internal == {harness.baseline.digest}

    final = service.status()
    assert _rollout_state(final).serving_digest == document["candidate_digest"]
    assert final["external_evidence_state"] == SloEvidenceState.EXTERNAL_VERIFIED.value
    # A fully rolled-out candidate is still not a certification claim.
    assert final["certified"] is False


def test_local_engineering_evidence_is_recorded_but_never_advances_serving(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    before = service.status()

    for index in range(4):
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
            evidence_state=SloEvidenceState.LOCAL_ENGINEERING,
            report_id=f"local-report-{index}",
        )
        status = service.advance()
        assert status["last_action"] == "LOCAL_SHADOW_WINDOW"

    after = service.status()
    assert after["sequence"] == before["sequence"] + 4
    assert after["external_evidence_state"] == "LOCAL_ENGINEERING_ONLY"
    # Four local windows and the phase, passes and serving digest are untouched.
    assert _rollout_state(after) == _rollout_state(before)


def test_an_approval_phase_ceiling_holds_the_rollout_at_its_limit(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.stage_observation(store)
    document = service.propose()
    _, approval_digest = harness.approve(
        store, document, maximum_phase=RolloutPhase.SHADOW
    )
    service.install(str(document["proposal_digest"]))

    actions: list[str] = []
    for index in range(4):
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
            report_id=f"capped-report-{index}",
        )
        actions.append(str(service.advance()["last_action"]))

    assert "APPROVAL_PHASE_LIMIT_HOLD" in actions
    state = _rollout_state(service.status())
    # The ceiling is honoured: SHADOW never becomes INTERNAL, so the candidate
    # is never served, no matter how many passing windows arrive.
    assert state.phase is RolloutPhase.SHADOW
    assert state.serving_digest == harness.baseline.digest


def test_replaying_one_evidence_window_cannot_double_count_a_pass(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=service.status(),
    )
    first = service.advance()
    replayed = service.advance()
    assert replayed == first
    assert _rollout_state(first).consecutive_passes == 1


# ==========================================================================
# 2. rollback
# ==========================================================================
def test_operator_rollback_returns_to_baseline_and_leaves_no_live_candidate(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    # Advance out of shadow so the candidate is genuinely being served first.
    for index in range(4):
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
            report_id=f"pre-rollback-{index}",
        )
        service.advance()
    served = _rollout_state(service.status())
    assert served.serving_digest == document["candidate_digest"]

    rolled = service.rollback(RollbackReason.SLO_BREACH)
    state = _rollout_state(rolled)
    assert rolled["last_action"] == "OPERATOR_ROLLBACK"
    assert state.candidate_digest is None
    assert state.serving_digest == harness.baseline.digest
    assert state.phase is RolloutPhase.OBSERVE
    assert state.rollback_reason is RollbackReason.SLO_BREACH
    assert state.consecutive_passes == 0
    assert state.epoch == served.epoch + 1


def test_a_rolled_back_candidate_is_not_resurrected_by_later_evidence(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    """Rollback is terminal for that candidate until it is installed again.

    The dangerous failure is a superseded candidate creeping back into the
    serving digest because a window signed against the pre-rollback state is
    still in flight.
    """

    document, approval_digest = _installed(harness, store, service)
    stale_status = service.status()
    service.rollback(RollbackReason.FALSE_HIT)
    after_rollback = service.status()

    # A window signed against the superseded head is refused outright.
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=stale_status,
        report_id="stale-window",
    )
    assert service.advance() == after_rollback

    # And a window signed against the *current* head is a no-op too, because
    # there is no candidate to advance.
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=after_rollback,
        report_id="post-rollback-window",
    )
    assert service.advance() == after_rollback

    state = _rollout_state(service.status())
    assert state.candidate_digest is None
    assert state.serving_digest == harness.baseline.digest
    assert document["candidate_digest"] != state.serving_digest


def test_rollback_is_idempotent_for_the_same_reason_and_appends_for_a_new_one(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    _installed(harness, store, service)
    first = service.rollback(RollbackReason.COST_GUARDRAIL)
    again = service.rollback(RollbackReason.COST_GUARDRAIL)
    assert again == first

    escalated = service.rollback(RollbackReason.CROSS_TENANT_HIT)
    assert escalated["sequence"] == first["sequence"] + 1
    assert _rollout_state(escalated).rollback_reason is RollbackReason.CROSS_TENANT_HIT


def test_a_safety_trigger_in_signed_evidence_rolls_back_automatically(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    report = harness.parity_report(
        report_id="cross-tenant-report",
        approval_digest=approval_digest,
        configuration_digest=str(document["candidate_digest"]),
        metrics_override={"cross_tenant_hits": 1},
    )
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=service.status(),
        report=report,
    )
    status = service.advance()
    assert status["last_action"] == "AUTOMATIC_ROLLBACK"
    state = _rollout_state(status)
    assert state.rollback_reason is RollbackReason.CROSS_TENANT_HIT
    assert state.candidate_digest is None
    assert state.serving_digest == harness.baseline.digest


def test_an_expired_approval_rolls_the_candidate_back_instead_of_advancing(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=service.status(),
    )
    harness.clock.advance(7_200)  # the approval's validity window has closed

    status = service.advance()
    assert status["last_action"] == "APPROVAL_INVALID_ROLLBACK"
    state = _rollout_state(status)
    assert state.rollback_reason is RollbackReason.APPROVAL_INVALID
    assert state.candidate_digest is None
    assert state.serving_digest == harness.baseline.digest


def test_a_rolled_back_candidate_can_be_installed_again_on_a_fresh_epoch(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, _ = _installed(harness, store, service)
    rolled = service.rollback(RollbackReason.SLO_BREACH)
    reinstalled = service.install(str(document["proposal_digest"]))

    state = _rollout_state(reinstalled)
    assert state.candidate_digest == document["candidate_digest"]
    assert state.phase is RolloutPhase.SHADOW
    assert state.serving_digest == harness.baseline.digest
    # A re-install is a new epoch and clears the stale rollback verdict.
    assert state.epoch == _rollout_state(rolled).epoch + 1
    assert state.rollback_reason is None


# ==========================================================================
# 3. illegal transitions fail closed with the module's own error codes
# ==========================================================================
def test_installing_an_unknown_proposal_is_not_found(
    service: CacheSloControlService
) -> None:
    with pytest.raises(NotFound) as raised:
        service.install(sha256_bytes(b"no such proposal"))
    assert raised.value.code == ErrorCode.NOT_FOUND


def test_installing_a_malformed_proposal_digest_is_refused(
    service: CacheSloControlService
) -> None:
    from elmos_build_cache.errors import DigestMismatch

    with pytest.raises(DigestMismatch) as raised:
        service.install("not-a-digest")
    assert raised.value.code == ErrorCode.DIGEST_MISMATCH


def test_installing_without_an_operator_approval_is_permission_denied(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.stage_observation(store)
    document = service.propose()
    with pytest.raises(PermissionDenied) as raised:
        service.install(str(document["proposal_digest"]))
    assert raised.value.code == ErrorCode.PERMISSION_DENIED
    # No approval means no durable transition at all.
    assert service.status()["sequence"] == 1


def test_an_approval_signed_by_the_wrong_key_is_provenance_invalid(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.stage_observation(store)
    document = service.propose()
    impostor = Ed25519ProvenanceSigner.generate("impostor-key")
    harness.approve(store, document, signer=impostor)
    with pytest.raises(ProvenanceInvalid) as raised:
        service.install(str(document["proposal_digest"]))
    assert raised.value.code == ErrorCode.PROVENANCE_INVALID
    assert service.status()["sequence"] == 1


def test_an_approval_whose_receipt_was_never_published_is_not_found(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.stage_observation(store)
    document = service.propose()
    harness.approve(store, document, register=False)
    with pytest.raises(NotFound) as raised:
        service.install(str(document["proposal_digest"]))
    assert raised.value.code == ErrorCode.NOT_FOUND


def test_replacing_an_installed_candidate_without_rolling_back_is_a_conflict(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    _installed(harness, store, service)

    # A second, genuinely different candidate derived from a second observation.
    harness.stage_observation(store, _observation(storage_pressure=0.95))
    rival = service.propose()
    harness.approve(store, rival)
    assert rival["candidate_digest"] != service.status()["state"]["candidate_digest"]

    with pytest.raises(ConflictError) as raised:
        service.install(str(rival["proposal_digest"]))
    assert raised.value.code == ErrorCode.CONFLICT
    assert service.status()["sequence"] == 2


def test_an_approval_that_does_not_permit_shadow_cannot_be_minted(
    harness: Harness, store: SqliteMetadataStore, service: CacheSloControlService
) -> None:
    harness.stage_observation(store)
    document = service.propose()
    with pytest.raises(ContractViolation) as raised:
        harness.approve(store, document, maximum_phase=RolloutPhase.OBSERVE)
    assert raised.value.code == ErrorCode.CONTRACT_VIOLATION


def test_an_observation_collector_cannot_also_be_its_own_verifier(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    with pytest.raises(ContractViolation) as raised:
        harness.stage_observation(store, collector=COLLECTOR, verifier=COLLECTOR)
    assert raised.value.code == ErrorCode.CONTRACT_VIOLATION


def test_evidence_whose_executor_verified_itself_cannot_be_minted(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    with pytest.raises(ContractViolation) as raised:
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
            executor=EXECUTOR,
            verifier=EXECUTOR,
        )
    assert raised.value.code == ErrorCode.CONTRACT_VIOLATION


def test_evidence_signed_by_the_wrong_key_is_provenance_invalid(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    impostor = Ed25519ProvenanceSigner.generate("impostor-evidence-key")
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=service.status(),
        signer=impostor,
    )
    with pytest.raises(ProvenanceInvalid) as raised:
        service.advance()
    assert raised.value.code == ErrorCode.PROVENANCE_INVALID
    assert service.status()["sequence"] == 2


def test_external_evidence_not_bound_to_scope_and_approval_is_refused(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    """An unauthenticated parity report may never be promoted to external."""

    document, approval_digest = _installed(harness, store, service)
    unbound = harness.parity_report(
        report_id="unauthenticated-report",
        approval_digest=approval_digest,
        configuration_digest=str(document["candidate_digest"]),
        authenticated=False,
    )
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=service.status(),
        report=unbound,
    )
    with pytest.raises(ProvenanceInvalid) as raised:
        service.advance()
    assert raised.value.code == ErrorCode.PROVENANCE_INVALID
    assert service.status()["sequence"] == 2


def test_evidence_bound_to_a_different_configuration_is_refused(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    mismatched = harness.parity_report(
        report_id="wrong-configuration-report",
        approval_digest=approval_digest,
        configuration_digest=harness.baseline.digest,
    )
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=service.status(),
        report=mismatched,
    )
    with pytest.raises(ProvenanceInvalid) as raised:
        service.advance()
    assert raised.value.code == ErrorCode.PROVENANCE_INVALID


def test_evidence_signed_against_a_superseded_head_is_refused(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    document, approval_digest = _installed(harness, store, service)
    stale = service.status()
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=stale,
        report_id="first-window",
    )
    service.advance()

    # Same signed window, now describing a head that is no longer current.
    harness.stage_window(
        store,
        document=document,
        approval_digest=approval_digest,
        status=stale,
        report_id="replayed-against-stale-head",
    )
    with pytest.raises(ProvenanceInvalid) as raised:
        service.advance()
    assert raised.value.code == ErrorCode.PROVENANCE_INVALID


def test_a_symmetric_trust_root_cannot_anchor_the_control_plane(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    weak = HmacProvenanceSigner({"shared": b"0" * 32}, "shared")
    with pytest.raises(ProvenanceInvalid) as raised:
        harness.service(store, approval_verifier=weak)
    assert raised.value.code == ErrorCode.PROVENANCE_INVALID


def test_a_controller_cannot_be_rebound_to_a_different_baseline(
    harness: Harness, store: SqliteMetadataStore, service: CacheSloControlService
) -> None:
    assert service.status()["sequence"] == 1
    other = replace(harness.baseline, capacity_bytes=harness.baseline.capacity_bytes * 2)
    with pytest.raises(ContractViolation) as raised:
        harness.service(store, baseline=other)
    assert raised.value.code == ErrorCode.CONTRACT_VIOLATION


def test_a_non_positive_required_window_count_is_refused(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    with pytest.raises(ContractViolation) as raised:
        harness.service(store, required_windows=0)
    assert raised.value.code == ErrorCode.CONTRACT_VIOLATION


def test_a_controller_scope_that_does_not_exist_is_not_found(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    with pytest.raises(NotFound) as raised:
        harness.service(store, project_id="project-never-created")
    assert raised.value.code == ErrorCode.NOT_FOUND


def test_an_approval_receipt_cannot_be_silently_replaced(
    service: CacheSloControlService, harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.stage_observation(store)
    document = service.propose()
    harness.approve(store, document, approver=APPROVER)
    with pytest.raises(IdempotencyConflict) as raised:
        harness.approve(store, document, approver="someone-else")
    assert raised.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


# ==========================================================================
# 4. concurrency
# ==========================================================================
def _race(
    harness: Harness, first: RollbackReason, second: RollbackReason
) -> tuple[list[str], list[BaseException]]:
    """Run two independent writers at one head; return winners and losers.

    Each worker owns its own connection because SQLite connections are
    thread-bound -- which is also what makes this a real two-writer race rather
    than two calls serialised behind one store's lock.
    """

    barrier = threading.Barrier(2)
    winners: list[str] = []
    losers: list[BaseException] = []
    guard = threading.Lock()

    def worker(reason: RollbackReason) -> None:
        opened = harness.open_store()
        try:
            controller = harness.service(opened)
            barrier.wait(timeout=30)
            try:
                status = controller.rollback(reason)
            except BaseException as failure:  # noqa: BLE001 - the point of the test
                with guard:
                    losers.append(failure)
            else:
                with guard:
                    winners.append(str(status["state"]["rollback_reason"]))
        finally:
            opened.close()

    threads = [
        threading.Thread(target=worker, args=(first,)),
        threading.Thread(target=worker, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
        assert not thread.is_alive()
    return winners, losers


def test_two_concurrent_writers_cannot_both_win_the_same_head(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    service = harness.service(store)
    document, _ = _installed(harness, store, service)
    head_before = service.status()
    store.close()

    winners, losers = _race(
        harness, RollbackReason.SLO_BREACH, RollbackReason.COST_GUARDRAIL
    )
    assert len(winners) == 1
    assert len(losers) == 1
    loser = losers[0]
    assert isinstance(loser, ConflictError)
    assert loser.code == ErrorCode.CONFLICT

    # Reopen: only what actually persisted counts.
    reopened = harness.open_store()
    try:
        rows = reopened.query(
            "SELECT sequence, action, document FROM cache_slo_control_events_v12"
            " WHERE tenant_id=? AND project_id=? AND controller_id=? ORDER BY sequence",
            (harness.tenant_id, harness.project_id, harness.controller_id),
        )
        assert [int(row[0]) for row in rows] == [1, 2, 3]
        assert str(rows[-1][1]) == "OPERATOR_ROLLBACK"
        durable = harness.service(reopened).status()
    finally:
        reopened.close()

    state = _rollout_state(durable)
    # Exactly one of the two legal outcomes, never a blend of both.
    assert str(state.rollback_reason) == winners[0]
    assert state.rollback_reason in {
        RollbackReason.SLO_BREACH,
        RollbackReason.COST_GUARDRAIL,
    }
    assert state.candidate_digest is None
    assert state.serving_digest == harness.baseline.digest
    assert state.epoch == _rollout_state(head_before).epoch + 1
    assert document["candidate_digest"] != state.serving_digest


def test_a_concurrency_loser_never_forks_the_event_chain(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    """Repeat the race; the durable chain must stay single and contiguous."""

    service = harness.service(store)
    document, _ = _installed(harness, store, service)
    store.close()

    for _ in range(6):
        winners, losers = _race(
            harness, RollbackReason.FALSE_HIT, RollbackReason.CORRUPT_EXECUTION
        )
        # The *outcome* of the race is not asserted, and deliberately so. A
        # ``threading.Barrier`` synchronises the start, not the transactions: on
        # a fast host the first writer can commit before the second has read the
        # head, and the second then legitimately appends a second rollback to
        # the new head. That is two writers serialising, not a fork -- and this
        # test is named for the fork. Asserting ``len(winners) == 1`` asserted
        # the scheduler instead, and duly failed on a Mac (2 winners) while
        # passing on the container.
        #
        # What must hold on every round, whichever way the race lands:
        assert len(winners) + len(losers) == 2, (winners, losers)
        # someone made progress -- the head cannot refuse both writers
        assert winners, losers
        # and a loser fails *cleanly*. This is the real safety property: losing
        # a write race must surface as the store's own conflict, never as a
        # torn transaction or a contract violation from a half-written chain.
        assert all(isinstance(failure, ConflictError) for failure in losers), losers

        reopened = harness.open_store()
        try:
            rows = reopened.query(
                "SELECT sequence, event_digest, previous_event_digest FROM"
                " cache_slo_control_events_v12 WHERE tenant_id=? AND project_id=?"
                " AND controller_id=? ORDER BY sequence",
                (harness.tenant_id, harness.project_id, harness.controller_id),
            )
            # One row per sequence number, and every link points at its parent.
            # This is what "never forks" means, and it is checked whether the
            # round produced one winner or two: a fork would show up either as a
            # duplicated sequence number or as a child whose parent digest does
            # not match the row before it.
            assert [int(row[0]) for row in rows] == list(range(1, len(rows) + 1))
            assert rows[0][2] is None
            for parent, child in zip(rows, rows[1:], strict=False):
                assert str(child[2]) == str(parent[1])
            # And the service still reads the chain without a contract error.
            reader = harness.service(reopened)
            reader.status()
            # Re-arm: put a live candidate back at the head so the next round
            # is a genuine two-writer contest rather than two idempotent no-ops.
            reader.install(str(document["proposal_digest"]))
        finally:
            reopened.close()


def test_the_event_journal_refuses_in_place_edits_and_deletes(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    """Durable history is append-only, enforced below the application."""

    service = harness.service(store)
    _installed(harness, store, service)

    with pytest.raises(sqlite3.IntegrityError, match="immutable"), store.transaction():
        store.execute(
            "UPDATE cache_slo_control_events_v12 SET action='TAMPERED'"
            " WHERE tenant_id=? AND sequence=1",
            (harness.tenant_id,),
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"), store.transaction():
        store.execute(
            "DELETE FROM cache_slo_control_events_v12 WHERE tenant_id=? AND sequence=2",
            (harness.tenant_id,),
        )
    assert service.status()["last_action"] == "CANDIDATE_INSTALLED"


def test_a_second_genesis_event_cannot_fork_an_initialized_controller(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.service(store)
    with pytest.raises(sqlite3.IntegrityError, match="already initialized"), (
        store.transaction()
    ):
        store.execute(
            "INSERT INTO cache_slo_control_events_v12 (tenant_id,project_id,"
            "controller_id,principal_digest,sequence,previous_event_digest,"
            "event_digest,action,document,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                harness.tenant_id,
                harness.project_id,
                harness.controller_id,
                harness.principal_digest,
                1,
                None,
                sha256_bytes(b"forked genesis"),
                "INITIALIZED",
                "{}",
                "2026-08-20T12:00:00Z",
            ),
        )


# ==========================================================================
# 5. tenant isolation and the absence of an existence oracle
# ==========================================================================
def _failure_shape(raised: pytest.ExceptionInfo[Any]) -> tuple[str, str, str, str]:
    """Everything a caller can observe about a refusal, and nothing else."""

    error = raised.value
    return (
        type(error).__name__,
        str(error.code),
        error.message,
        repr(sorted(error.details.items())),
    )


def test_a_foreign_tenant_cannot_open_another_tenants_controller(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.service(store)  # tenant A's controller exists and is initialized
    with pytest.raises(NotFound) as raised:
        harness.service(store, tenant_id=OTHER_TENANT)
    assert raised.value.code == ErrorCode.NOT_FOUND


def test_a_wrong_tenant_lookup_is_indistinguishable_from_an_absent_one(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    """The fail-closed path must not become an existence oracle.

    If probing another tenant's *existing* controller failed differently from
    probing a project that was never created, the difference alone would leak
    that the first one exists.
    """

    harness.service(store)
    with store.transaction():
        store.ensure_project(OTHER_TENANT, OTHER_PROJECT)

    with pytest.raises(NotFound) as foreign:
        harness.service(store, tenant_id=OTHER_TENANT)
    with pytest.raises(NotFound) as absent:
        harness.service(store, tenant_id=OTHER_TENANT, project_id="project-never-made")
    with pytest.raises(NotFound) as vacant:
        harness.service(
            store, tenant_id="tenant-never-made", project_id="project-never-made"
        )

    assert _failure_shape(foreign) == _failure_shape(absent) == _failure_shape(vacant)


def test_a_foreign_principal_cannot_prove_a_controller_exists(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    harness.service(store)
    intruder = _principal("principal-intruder")

    with pytest.raises(NotFound) as claimed:
        harness.service(store, principal_digest=intruder)
    # The same principal against a controller identifier that was never used
    # simply creates its own chain, so the *only* observable difference is a
    # refusal -- never a partial read of the other principal's state.
    fresh = harness.service(
        store, principal_digest=intruder, controller_id="controller-unused"
    )
    assert fresh.status()["sequence"] == 1
    assert claimed.value.code == ErrorCode.NOT_FOUND


def test_a_foreign_tenant_can_neither_read_nor_mutate_another_tenants_state(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    owner = harness.service(store)
    document, _ = _installed(harness, store, owner)
    owner_status = owner.status()

    with store.transaction():
        store.ensure_project(OTHER_TENANT, OTHER_PROJECT)
    intruder_harness = replace(
        harness,
        tenant_id=OTHER_TENANT,
        project_id=OTHER_PROJECT,
        principal_digest=_principal("principal-b"),
        resolver=StaticSloApprovalResolver(),
        observations=_Value(),
        windows=_Value(),
    )
    intruder = intruder_harness.service(store)

    # The intruder's controller shares a controller_id but starts empty.
    assert intruder.status()["sequence"] == 1
    assert _rollout_state(intruder.status()).candidate_digest is None

    # It cannot resolve the owner's proposal, even with the exact digest.
    with pytest.raises(NotFound) as raised:
        intruder.install(str(document["proposal_digest"]))
    assert raised.value.code == ErrorCode.NOT_FOUND

    # Nor can it roll the owner's rollout back.
    intruder.rollback(RollbackReason.SLO_BREACH)
    assert owner.status() == owner_status
    assert _rollout_state(owner.status()).candidate_digest == document["candidate_digest"]


def test_the_owners_signed_artifacts_are_invisible_to_another_tenant(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    owner = harness.service(store)
    trusted = harness.stage_observation(store)
    document = owner.propose()

    with store.transaction():
        store.ensure_project(OTHER_TENANT, OTHER_PROJECT)
    for digest in (trusted.artifact_digest, str(document["artifact_digest"])):
        assert store.get_artifact(harness.tenant_id, digest) is not None
        # Same content address, different tenant: no row, so no read.
        assert store.get_artifact(OTHER_TENANT, digest) is None
    assert store.artifact_targets(
        OTHER_TENANT,
        "cache-slo-proposal",
        f"{harness.project_id}:{harness.controller_id}:{document['proposal_digest']}",
    ) == []


def test_the_composite_scope_key_refuses_a_row_naming_a_foreign_project(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    """The database, not just the application, binds a controller to a tenant."""

    harness.service(store)
    with store.transaction():
        store.ensure_project(OTHER_TENANT, OTHER_PROJECT)

    with pytest.raises(sqlite3.IntegrityError), store.transaction():
        store.execute(
            "INSERT INTO cache_slo_control_events_v12 (tenant_id,project_id,"
            "controller_id,principal_digest,sequence,previous_event_digest,"
            "event_digest,action,document,recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                OTHER_TENANT,
                harness.project_id,  # a project this tenant does not own
                "controller-smuggled",
                _principal("principal-b"),
                1,
                None,
                sha256_bytes(b"smuggled"),
                "INITIALIZED",
                "{}",
                "2026-08-20T12:00:00Z",
            ),
        )
    assert (
        store.query_one(
            "SELECT COUNT(*) FROM cache_slo_control_events_v12 WHERE tenant_id=?",
            (OTHER_TENANT,),
        )
        == (0,)
    )


def test_the_runtime_registry_refuses_every_scope_it_was_not_given(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    registry = CacheSloRuntimeRegistry()
    service = harness.service(store)
    registry.register(service, principal_digest=harness.principal_digest)

    assert (
        registry.service(
            harness.tenant_id,
            harness.project_id,
            harness.controller_id,
            harness.principal_digest,
        )
        is service
    )

    shapes = []
    for tenant, project, controller, principal in (
        (OTHER_TENANT, harness.project_id, harness.controller_id, harness.principal_digest),
        (harness.tenant_id, OTHER_PROJECT, harness.controller_id, harness.principal_digest),
        (harness.tenant_id, harness.project_id, "controller-absent", harness.principal_digest),
        (
            harness.tenant_id,
            harness.project_id,
            harness.controller_id,
            _principal("principal-intruder"),
        ),
    ):
        with pytest.raises(NotFound) as raised:
            registry.service(tenant, project, controller, principal)
        shapes.append(_failure_shape(raised))
    # A wrong principal on a real controller is indistinguishable from a scope
    # that was never registered at all.
    assert len(set(shapes)) == 1


def test_a_runtime_registration_cannot_be_rebound_to_another_principal(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    registry = CacheSloRuntimeRegistry()
    service = harness.service(store)
    registry.register(service, principal_digest=harness.principal_digest)

    with pytest.raises(PermissionDenied) as denied:
        registry.register(service, principal_digest=_principal("principal-intruder"))
    assert denied.value.code == ErrorCode.PERMISSION_DENIED

    # Re-registering the very same service is idempotent ...
    registry.register(service, principal_digest=harness.principal_digest)
    assert (
        registry.service(
            harness.tenant_id,
            harness.project_id,
            harness.controller_id,
            harness.principal_digest,
        )
        is service
    )

    # ... but a *different* controller object cannot silently take the scope.
    usurper = harness.service(store)
    assert usurper is not service
    with pytest.raises(IdempotencyConflict) as conflict:
        registry.register(usurper, principal_digest=harness.principal_digest)
    assert conflict.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    assert (
        registry.service(
            harness.tenant_id,
            harness.project_id,
            harness.controller_id,
            harness.principal_digest,
        )
        is service
    )


# ==========================================================================
# 6. migration mirrors and the exact schema the module reads and writes
# ==========================================================================
class _RecordingStore(SqliteMetadataStore):
    """A real store that also keeps every statement the module issued."""

    def __init__(self, connection: Any, clock: ManualClock) -> None:
        super().__init__(connection, clock)
        self.statements: list[str] = []

    def execute(self, statement: str, params: Sequence[Any] = ()) -> Any:
        self.statements.append(statement)
        return super().execute(statement, params)


def _control_event_columns_used_by_the_module(root: Path, clock: ManualClock) -> set[str]:
    """Derive the touched column set by watching a real lifecycle run."""

    cas = ContentAddressableStore(root / "cas")
    harness = Harness(root=root / "slo", clock=clock, cas=cas)
    harness.root.mkdir(parents=True, exist_ok=True)
    bootstrap = SqliteMetadataStore.open(harness.database, clock)
    try:
        with bootstrap.transaction():
            bootstrap.ensure_project(harness.tenant_id, harness.project_id)
    finally:
        bootstrap.close()

    connection = sqlite3.connect(str(harness.database), timeout=30.0, isolation_level="DEFERRED")
    for pragma in store_module.SQLITE_PRAGMAS:
        connection.execute(pragma)
    store = _RecordingStore(connection, clock)
    try:
        service = harness.service(store)
        document, approval_digest = _installed(harness, store, service)
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
        )
        service.advance()
        service.rollback(RollbackReason.SLO_BREACH)
        declared = {
            str(row[1]) for row in store.query(f"PRAGMA table_info({CONTROL_EVENTS_TABLE})")
        }
        touched: set[str] = set()
        for statement in store.statements:
            if CONTROL_EVENTS_TABLE not in statement:
                continue
            words = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", statement))
            touched |= words & declared
        assert touched, "the module issued no statement against the control table"
        return touched
    finally:
        store.close()


def test_the_slo_migration_is_byte_identical_to_its_packaged_mirror() -> None:
    repository = Path(__file__).resolve().parents[1] / "migrations"
    for dialect, name in (
        ("sqlite", SLO_SQLITE_MIGRATION),
        ("postgres", SLO_POSTGRES_MIGRATION),
    ):
        published = (repository / dialect / name).read_bytes()
        packaged = (store_module.MIGRATIONS_DIR / dialect / name).read_bytes()
        assert published == packaged
        assert published, "an empty migration would silently install nothing"


def test_the_slo_migration_is_the_contiguous_tail_of_both_dialects() -> None:
    for names, migration in (
        (store_module.SQLITE_MIGRATIONS, SLO_SQLITE_MIGRATION),
        (store_module.POSTGRES_MIGRATIONS, SLO_POSTGRES_MIGRATION),
    ):
        assert names[-1] == migration
        assert [int(name[:4]) for name in names] == list(range(1, len(names) + 1))
        assert len(set(names)) == len(names)


def test_applying_the_slo_migration_produces_exactly_the_schema_the_module_uses(
    tmp_path: Path, clock: ManualClock
) -> None:
    """Build the previous schema by hand, then apply 0007 and check every part.

    The column list is not written down twice: it is derived by recording the
    SQL the service actually issues during a full lifecycle, so a column the
    module stops using -- or starts using -- changes this assertion.
    """

    used = _control_event_columns_used_by_the_module(tmp_path / "derived", clock)

    path = tmp_path / "stepwise.sqlite"
    connection = sqlite3.connect(str(path))
    try:
        migrations = store_module.SQLITE_MIGRATIONS
        assert migrations[-1] == SLO_SQLITE_MIGRATION
        for name in migrations[:-1]:
            connection.executescript(
                (store_module.MIGRATIONS_DIR / "sqlite" / name).read_text(encoding="utf-8")
            )
        # The previous migration must not already provide the table, or 0007
        # would be asserting nothing.
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE name=?", (CONTROL_EVENTS_TABLE,)
            ).fetchone()
            is None
        )
        connection.executescript(
            (store_module.MIGRATIONS_DIR / "sqlite" / SLO_SQLITE_MIGRATION).read_text(
                encoding="utf-8"
            )
        )

        info = connection.execute(f"PRAGMA table_info({CONTROL_EVENTS_TABLE})").fetchall()
        columns = {str(row[1]): (str(row[2]), bool(row[3])) for row in info}
        # Every column the module touches exists, and the table carries nothing
        # the module does not touch.
        assert used == set(columns)
        assert columns == {
            "tenant_id": ("TEXT", True),
            "project_id": ("TEXT", True),
            "controller_id": ("TEXT", True),
            "principal_digest": ("TEXT", True),
            "sequence": ("INTEGER", True),
            "previous_event_digest": ("TEXT", False),
            "event_digest": ("TEXT", True),
            "action": ("TEXT", True),
            "proposal_digest": ("TEXT", False),
            "approval_digest": ("TEXT", False),
            "evidence_digest": ("TEXT", False),
            "evidence_state": ("TEXT", False),
            "document": ("TEXT", True),
            "recorded_at": ("TEXT", True),
        }

        indexes = {
            str(row[1]): (bool(row[2]), bool(row[4]))
            for row in connection.execute(f"PRAGMA index_list({CONTROL_EVENTS_TABLE})")
        }
        members = {
            name: [
                str(row[2])
                for row in connection.execute(f"PRAGMA index_info('{name}')")  # noqa: S608
            ]
            for name in indexes
        }
        primary = next(name for name in indexes if name.endswith("_1") and indexes[name][0])
        assert members[primary] == ["tenant_id", "project_id", "controller_id", "sequence"]
        unique_event = next(
            name
            for name, columns_ in members.items()
            if columns_ == ["tenant_id", "project_id", "controller_id", "event_digest"]
        )
        assert indexes[unique_event][0] is True
        assert members["idx_cache_slo_control_events_scope"] == [
            "tenant_id",
            "project_id",
            "controller_id",
            "principal_digest",
            "sequence",
        ]
        # The evidence index is unique *and partial*, so many NULL evidence
        # rows coexist while one evidence digest can never be counted twice.
        assert members["uq_cache_slo_control_events_evidence"] == [
            "tenant_id",
            "project_id",
            "controller_id",
            "evidence_digest",
        ]
        assert indexes["uq_cache_slo_control_events_evidence"] == (True, True)

        foreign_keys = [
            (str(row[2]), str(row[3]), str(row[4]), str(row[5]), str(row[6]))
            for row in connection.execute(
                f"PRAGMA foreign_key_list({CONTROL_EVENTS_TABLE})"
            )
        ]
        assert sorted(foreign_keys) == [
            ("projects", "project_id", "project_id", "RESTRICT", "RESTRICT"),
            ("projects", "tenant_id", "tenant_id", "RESTRICT", "RESTRICT"),
        ]

        definition = str(
            connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (CONTROL_EVENTS_TABLE,),
            ).fetchone()[0]
        )
        assert "CHECK (sequence > 0)" in definition
        assert "evidence_state IS NULL OR evidence_state IN" in definition
        assert "(sequence = 1 AND previous_event_digest IS NULL)" in definition

        triggers = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
                (CONTROL_EVENTS_TABLE,),
            )
        }
        assert triggers == {
            "trg_cache_slo_control_events_chain_insert",
            "trg_cache_slo_control_events_immutable_update",
            "trg_cache_slo_control_events_immutable_delete",
        }
        # Record what was applied by hand so reopening does not re-run it.
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations"
            " (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            ((name, "hand-applied") for name in migrations),
        )
        connection.commit()
    finally:
        connection.close()

    # The hand-migrated database is the one the service then runs against.
    reopened = SqliteMetadataStore.open(path, clock)
    try:
        applied = {
            str(row[0]) for row in reopened.query("SELECT name FROM schema_migrations")
        }
        # Opening the store found nothing left to do: the hand-applied schema
        # is exactly what the packaged migration list produces.
        assert applied == set(store_module.SQLITE_MIGRATIONS)
        harness = Harness(
            root=tmp_path / "handmade",
            clock=clock,
            cas=ContentAddressableStore(tmp_path / "handmade-cas"),
        )
        harness.root.mkdir(parents=True, exist_ok=True)
        with reopened.transaction():
            reopened.ensure_project(harness.tenant_id, harness.project_id)
        service = harness.service(reopened)
        document, approval_digest = _installed(harness, reopened, service)
        harness.stage_window(
            reopened,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
        )
        assert service.advance()["last_action"] == "EXTERNAL_WINDOW_ACCEPTED"
    finally:
        reopened.close()


def test_the_evidence_uniqueness_index_admits_many_nulls_but_one_digest(
    harness: Harness, store: SqliteMetadataStore
) -> None:
    """The partial unique index is what the replay guard actually rests on."""

    service = harness.service(store)
    _installed(harness, store, service)
    service.rollback(RollbackReason.SLO_BREACH)
    # Two events so far carry a NULL evidence digest and both persisted.
    assert store.query_one(
        "SELECT COUNT(*) FROM cache_slo_control_events_v12 WHERE tenant_id=?"
        " AND evidence_digest IS NULL",
        (harness.tenant_id,),
    ) == (3,)

    duplicate = sha256_bytes(b"one evidence window")
    for sequence in (10, 11):
        statement = (
            "INSERT INTO cache_slo_control_events_v12 (tenant_id,project_id,"
            "controller_id,principal_digest,sequence,previous_event_digest,"
            "event_digest,action,evidence_digest,document,recorded_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
        )
        params = (
            harness.tenant_id,
            harness.project_id,
            harness.controller_id,
            harness.principal_digest,
            sequence,
            sha256_bytes(f"parent-{sequence}".encode()),
            sha256_bytes(f"event-{sequence}".encode()),
            "EXTERNAL_WINDOW_ACCEPTED",
            duplicate,
            "{}",
            "2026-08-20T12:00:00Z",
        )
        with pytest.raises(sqlite3.IntegrityError), store.transaction():
            store.execute(statement, params)


# ==========================================================================
# 7. reopen durability
# ==========================================================================
def test_every_transition_survives_closing_and_reopening_the_store(
    harness: Harness
) -> None:
    """Write, close, reopen, read back -- byte for byte, at each step."""

    checkpoints: list[dict[str, Any]] = []

    store = harness.open_store()
    try:
        service = harness.service(store)
        checkpoints.append(service.status())
        document, approval_digest = _installed(harness, store, service)
        checkpoints.append(service.status())
        harness.stage_window(
            store,
            document=document,
            approval_digest=approval_digest,
            status=service.status(),
        )
        checkpoints.append(service.advance())
    finally:
        store.close()

    reopened = harness.open_store()
    try:
        recovered = harness.service(reopened)
        # The reopened controller reads the same head, not a re-initialised one.
        assert recovered.status() == checkpoints[-1]
        assert recovered.status()["sequence"] == 3

        # And every earlier event is still exactly what was written.
        rows = reopened.query(
            "SELECT sequence, event_digest, action, document FROM"
            " cache_slo_control_events_v12 WHERE tenant_id=? AND project_id=?"
            " AND controller_id=? ORDER BY sequence",
            (harness.tenant_id, harness.project_id, harness.controller_id),
        )
        assert [str(row[2]) for row in rows] == [
            "INITIALIZED",
            "CANDIDATE_INSTALLED",
            "EXTERNAL_WINDOW_ACCEPTED",
        ]
        for status, row in zip(checkpoints, rows, strict=True):
            assert str(row[1]) == status["event_digest"]

        # Continuing after the reopen extends the same chain.
        further = recovered.rollback(RollbackReason.SLO_BREACH)
        assert further["sequence"] == 4
    finally:
        reopened.close()

    final = harness.open_store()
    try:
        assert harness.service(final).status() == further
    finally:
        final.close()


def test_a_reopened_controller_rejects_a_tampered_event_document(
    harness: Harness
) -> None:
    """Durability is not enough; the chain has to still verify on the way back."""

    store = harness.open_store()
    try:
        service = harness.service(store)
        _installed(harness, store, service)
        head = service.status()
    finally:
        store.close()

    # Edit the journal underneath the application, bypassing its triggers.
    raw = sqlite3.connect(str(harness.database))
    try:
        raw.execute("DROP TRIGGER trg_cache_slo_control_events_immutable_update")
        raw.execute(
            "UPDATE cache_slo_control_events_v12 SET action='SILENTLY_PROMOTED'"
            " WHERE tenant_id=? AND sequence=2",
            (harness.tenant_id,),
        )
        raw.commit()
    finally:
        raw.close()

    reopened = harness.open_store()
    try:
        with pytest.raises(ContractViolation) as raised:
            harness.service(reopened)
        assert raised.value.code == ErrorCode.CONTRACT_VIOLATION
    finally:
        reopened.close()
    assert head["last_action"] == "CANDIDATE_INSTALLED"
