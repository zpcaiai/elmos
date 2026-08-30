from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import sqlite3

import pytest

from elmos_pdhi._catalog import SOURCE_CAPABILITY_CATALOG
from elmos_pdhi.certification import (
    CertificationEvaluator,
    ClaimStatus,
    EvidenceClaim,
    Finding,
    FindingSeverity,
    ReadinessState,
)
from elmos_pdhi.control_plane import (
    Invocation,
    K9_OPERATION_BINDINGS,
    OutcomeStatus,
    ProductionControlPlane,
    ProgressEstimate,
    QuotaPolicy,
)
from elmos_pdhi.contracts import CertificationLevel, CertificationVerdict, SkillLifecycleStatus, SkillManifest
from elmos_pdhi.errors import AuthorizationError, UnknownCapabilityError, ValidationError
from elmos_pdhi.evolution import (
    BenchmarkEvidence,
    FixtureRecord,
    K7_CAPABILITY_BINDINGS,
    LocalEvolutionRepository,
    SkillEvolutionService,
)
from elmos_pdhi.routing import (
    AppendOnlyContextLedger,
    CandidateAvailability,
    K8_CAPABILITY_BINDINGS,
    ModelCandidate,
    ModelRoleRouter,
    RouteStatus,
    RoutingPolicy,
    ToolAuthorityRouter,
    ToolCandidate,
)
from elmos_pdhi.store import (
    IdempotencyConflict,
    LeaseConflict,
    SCHEMA_VERSION,
    ScopeBinding,
    ScopeViolation,
    SqlitePdhiStore,
)
from elmos_pdhi.contracts import AuthorityLevel


NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def sha(label: str) -> str:
    return "sha256:" + (label.encode("utf-8").hex() * 64)[:64]


def scope(*, tenant: str = "tenant-a", project: str = "project-a", actor: str = "actor-a") -> ScopeBinding:
    return ScopeBinding(tenant, project, actor, sha("authority"), sha("environment"))


def manifest() -> SkillManifest:
    return SkillManifest(
        skill_id="candidate-skill",
        namespace="elmos.pdhi.test",
        name="candidate",
        version="1.0.0",
        status=SkillLifecycleStatus.DRAFT,
        triggers=("repair",),
        inputs={"type": "object"},
        outputs={"type": "object"},
        acceptance=("preserves invariant",),
    )


def claim(
    gate: CertificationLevel,
    obligation_id: str,
    *,
    external: bool = False,
    independent: bool = True,
    status: ClaimStatus = ClaimStatus.PASS,
    evidence_id: str | None = None,
    produced_at: datetime = NOW,
) -> EvidenceClaim:
    claim_id = evidence_id or f"{gate.value.lower()}-{obligation_id}"
    return EvidenceClaim(
        evidence_id=claim_id,
        artifact_digest=sha(f"artifact-{gate.value}-{obligation_id}"),
        gate=gate,
        obligation_id=obligation_id,
        producer_id="producer-a",
        verifier_id="verifier-b" if independent else None,
        status=status,
        produced_at=produced_at,
        input_digests=(sha(f"input-{gate.value}-{obligation_id}"),),
        tool_digest=sha("tool"),
        environment_digest=sha("environment"),
        independent=independent,
        external=external,
        authorization_id="external-auth" if external else None,
        verification_receipt_digest=sha(f"receipt-{claim_id}"),
        subject_revision=sha("source"),
    )


class TestClaimVerifier:
    __test__ = False

    @staticmethod
    def verify(evidence: EvidenceClaim) -> bool:
        return evidence.verification_receipt_digest == sha(f"receipt-{evidence.evidence_id}")


def test_sqlite_schema_migration_restart_and_tenant_isolation(tmp_path) -> None:
    path = tmp_path / "pdhi.sqlite"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE pdhi_schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
    connection.execute("INSERT INTO pdhi_schema_version(version, applied_at) VALUES (1, '2026-08-30T00:00:00Z')")
    connection.commit()
    connection.close()

    first = SqlitePdhiStore(path)
    assert first.schema_version == SCHEMA_VERSION == 2
    a, b = scope(), scope(tenant="tenant-b", project="project-b")
    first.register_scope(a, now=NOW)
    first.register_scope(b, now=NOW)
    created = first.create_job(a, job_id="job-a", input_revision=sha("input"), payload={"goal": "test"}, now=NOW)
    assert created["state"] == "QUEUED"
    with pytest.raises(ScopeViolation):
        first.get_job(b, "job-a")
    first.close()

    restored = SqlitePdhiStore(path)
    assert restored.get_job(a, "job-a")["version"] == 1
    assert restored.readiness()["status"] == "READY"
    restored.close()


def test_store_idempotency_lease_fence_effect_unknown_and_outbox(tmp_path) -> None:
    store = SqlitePdhiStore(tmp_path / "control.sqlite")
    binding = scope()
    store.register_scope(binding, now=NOW)
    initial = store.reserve_idempotency(binding, operation="operation", idempotency_key="key", request={"a": 1}, now=NOW)
    assert initial.created and not initial.in_progress
    blocked = store.reserve_idempotency(binding, operation="operation", idempotency_key="key", request={"a": 1}, now=NOW)
    assert not blocked.created and blocked.in_progress and blocked.response is None
    with pytest.raises(IdempotencyConflict):
        store.reserve_idempotency(binding, operation="operation", idempotency_key="key", request={"a": 2}, now=NOW)

    lease_one = store.acquire_lease(binding, resource_id="workspace", owner_id="worker-a", ttl=timedelta(seconds=1), now=NOW)
    lease_two = store.acquire_lease(binding, resource_id="workspace", owner_id="worker-b", ttl=timedelta(seconds=1), now=NOW + timedelta(seconds=2))
    with pytest.raises(LeaseConflict):
        store.verify_lease(binding, lease_one, now=NOW + timedelta(seconds=2))
    effect = store.prepare_effect(
        binding,
        effect_id="effect-a",
        job_id="job-a",
        operation="provider-request",
        idempotency_key="effect-key",
        request={"effect": "planned"},
        lease=lease_two,
        now=NOW + timedelta(seconds=2),
    )
    started = store.transition_effect(binding, effect_id=effect.effect_id, expected_version=effect.version, target_state="STARTED", now=NOW)
    unknown = store.transition_effect(binding, effect_id=effect.effect_id, expected_version=started.version, target_state="UNKNOWN", response={"outcome": "unreconciled"}, now=NOW)
    assert unknown.state == "UNKNOWN"
    with pytest.raises(LeaseConflict):
        store.transition_effect(binding, effect_id=effect.effect_id, expected_version=unknown.version, target_state="SUCCEEDED", now=NOW)
    other_scope = scope(tenant="tenant-b", project="project-b")
    store.register_scope(other_scope, now=NOW)
    assert store.claim_outbox(other_scope, worker_id="worker-b", now=NOW) == ()
    claims = store.claim_outbox(binding, worker_id="worker-a", now=NOW)
    assert claims
    with pytest.raises(LeaseConflict):
        store.acknowledge_outbox(other_scope, claims[0], worker_id="worker-a", delivered_at=NOW)
    store.acknowledge_outbox(binding, claims[0], worker_id="worker-a", delivered_at=NOW)
    with pytest.raises(LeaseConflict):
        store.acknowledge_outbox(binding, claims[0], worker_id="worker-a", delivered_at=NOW)
    store.close()


def test_k9_exact_bindings_idempotency_and_exact_decimal_controls(tmp_path) -> None:
    assert len(K9_OPERATION_BINDINGS) == len(SOURCE_CAPABILITY_CATALOG["K9"]) == 59
    assert set(K9_OPERATION_BINDINGS) == set(SOURCE_CAPABILITY_CATALOG["K9"])
    store = SqlitePdhiStore(tmp_path / "k9.sqlite")
    binding = scope()
    store.register_scope(binding, now=NOW)
    plane = ProductionControlPlane(store)
    invocation = Invocation(binding, "durable-job", "idem-job", {"job_id": "job-a", "input_revision": sha("input"), "job": {"goal": "test"}})
    first = plane.invoke(invocation)
    replay = plane.invoke(invocation)
    assert first.status is OutcomeStatus.COMPLETED
    assert replay.result["idempotent_replay"] is True
    pending = store.reserve_idempotency(binding, operation="K9:health-endpoint", idempotency_key="pending", request={})
    assert pending.created
    reconciled = plane.invoke(Invocation(binding, "health-endpoint", "pending", {}))
    assert reconciled.status is OutcomeStatus.BLOCKED_RECONCILIATION
    with pytest.raises(UnknownCapabilityError):
        plane.invoke(Invocation(binding, "not-an-operation", "nope", {}))

    quota = QuotaPolicy(1, Decimal("1.00"), "USD", 100, sha("quota-policy"))
    denied = quota.decide(active_jobs=1, current_cost=Decimal("0.99"), current_tokens=99, requested_cost=Decimal("0.02"), requested_tokens=2)
    assert denied["decision"] == "DENY"
    eta = ProgressEstimate(Decimal("5"), Decimal("10"), Decimal("10"), Decimal("0.1"), Decimal("4"), Decimal("2")).calculate()
    assert eta["progress_ratio"] == "0.500000"
    assert eta["eta_seconds"] == "20.400"
    with pytest.raises(ValidationError):
        QuotaPolicy(1, Decimal("1"), "USD", 1, sha("quota-policy")).decide(active_jobs=0, current_cost=Decimal("0"), current_tokens=0, requested_cost=1.0, requested_tokens=0)
    store.close()


def test_k7_evolution_is_scoped_and_requires_independent_holdout_evidence() -> None:
    assert len(K7_CAPABILITY_BINDINGS) == 23
    repository = LocalEvolutionRepository()
    service = SkillEvolutionService(repository)
    memory = service.record_memory(
        memory_id="memory-a",
        memory_type="failure",
        tenant_id="tenant-a",
        project_id="project-a",
        source_revision=sha("source"),
        payload={"trigger": "bad input", "invariant": "preserve type", "remediation": "validate"},
        evidence_ids=("evidence-a",),
        created_at=NOW,
    )
    assert service.extract_lesson(memory)["generalization_status"] == "REQUIRES_INDEPENDENT_CORPUS"
    candidate = service.create_candidate(candidate_id="candidate-a", tenant_id="tenant-a", project_id="project-a", manifest=manifest(), source_memory_ids=(memory.memory_id,), now=NOW)
    with pytest.raises(AuthorizationError):
        repository.get_candidate("candidate-a", "tenant-b", "project-a")
    experimental = service.transition(tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=candidate.version, target=SkillLifecycleStatus.EXPERIMENTAL)
    assert experimental.allowed
    current = repository.get_candidate("candidate-a", "tenant-a", "project-a")
    denied = service.transition(tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=current.version, target=SkillLifecycleStatus.REGRESSION_TESTED)
    assert not denied.allowed and "positive_and_negative_fixtures_required" in denied.reasons
    positive = service.add_fixture(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=current.version,
        fixture=FixtureRecord("positive", "positive", sha("positive-input"), sha("positive-output"), True, "fixture-positive"), now=NOW,
    )
    negative = service.add_fixture(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=positive.version,
        fixture=FixtureRecord("negative", "negative", sha("negative-input"), sha("negative-output"), True, "fixture-negative"), now=NOW,
    )
    corpus = service.attach_corpus(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=negative.version,
        corpus_digest=sha("corpus"), now=NOW,
    )
    regression = service.transition(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=corpus.version,
        target=SkillLifecycleStatus.REGRESSION_TESTED, now=NOW,
    )
    assert regression.allowed
    after_regression = repository.get_candidate("candidate-a", "tenant-a", "project-a")
    golden = service.add_fixture(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=after_regression.version,
        fixture=FixtureRecord("golden", "golden-route", sha("golden-input"), sha("golden-output"), True, "fixture-golden"), now=NOW,
    )
    holdout = service.add_fixture(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=golden.version,
        fixture=FixtureRecord("holdout", "holdout", sha("holdout-input"), sha("holdout-output"), True, "fixture-holdout"), now=NOW,
    )
    local_benchmark = BenchmarkEvidence("benchmark-local", sha("corpus"), holdout.content_digest(), Decimal("1"), Decimal("0"), False, "same-org", "same-org", "benchmark-local")
    benchmarked = service.record_benchmark(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=holdout.version,
        evidence=local_benchmark, now=NOW,
    )
    blocked_golden = service.transition(
        tenant_id="tenant-a", project_id="project-a", candidate_id="candidate-a", expected_version=benchmarked.version,
        target=SkillLifecycleStatus.GOLDEN_ROUTE_TESTED, now=NOW,
    )
    assert not blocked_golden.allowed and "independent_zero_regression_benchmark_required" in blocked_golden.reasons


def test_k8_routing_context_and_prompt_never_silently_downgrade() -> None:
    assert len(K8_CAPABILITY_BINDINGS) == 42
    policy = RoutingPolicy("policy", sha("policy"), "tenant-a", frozenset({"approved"}), frozenset({"model"}), frozenset({"provider"}), AuthorityLevel.COMPILER, Decimal("0.8"), Decimal("1"), 1000, "restricted")
    low_authority = ToolCandidate("approved", "1.0.0", sha("tool"), AuthorityLevel.TEXT_SEARCH, frozenset({"search"}), frozenset({"tenant-a"}), ("src",), False, False, Decimal("1"), Decimal("0"), 1)
    decision = ToolAuthorityRouter().route(capability="search", path="src/a.py", required_authority=AuthorityLevel.COMPILER, policy=policy, candidates=(low_authority,))
    assert decision.status is RouteStatus.NOT_RUN
    assert "authority_too_low" in decision.rejected["approved"]
    exhausted = ModelCandidate("model", "provider", "1.0.0", sha("model"), frozenset({"analysis"}), 5, "restricted", frozenset({"tenant-a"}), ("src",), Decimal("0.9"), Decimal("0"), Decimal("0"), 1, CandidateAvailability.QUOTA_EXHAUSTED)
    model_decision = ModelRoleRouter().route(role="analysis", effort=5, path="src/a.py", estimated_tokens=1, policy=policy, candidates=(exhausted,))
    assert model_decision.status is RouteStatus.NOT_RUN
    assert "availability:QUOTA_EXHAUSTED" in model_decision.rejected["model"]
    with pytest.raises(ValidationError):
        ToolAuthorityRouter().route(capability="search", path="src/../secret.py", required_authority=AuthorityLevel.COMPILER, policy=policy, candidates=(low_authority,))

    ledger = AppendOnlyContextLedger(maximum_entries=3)
    ledger.append(entry_id="required", kind="constraint", payload={"value": "keep"}, required=True, source_digest=sha("required"))
    checkpoint = ledger.checkpoint(checkpoint_id="checkpoint", invariant_ids=("tenant-isolation",))
    with pytest.raises(ValidationError):
        ledger.compact(through_sequence=1, summary_id="bad-summary", summary={"preserved_required_entry_ids": ()}, source_digest=sha("summary"))
    summary = ledger.compact(through_sequence=1, summary_id="summary", summary={"preserved_required_entry_ids": ("required",)}, source_digest=sha("summary"))
    assert summary.required and ledger.rebuild(checkpoint.checkpoint_id)["entries"][0].entry_id == "required"


def test_k10_fails_closed_for_local_missing_independence_and_open_p0_p1() -> None:
    unsigned = CertificationEvaluator().evaluate(
        project_id="project-a",
        job_id="job-a",
        source_revision=sha("source"),
        target_revision=sha("target"),
        target_level=CertificationLevel.E0,
        claims=tuple(claim(CertificationLevel.E0, obligation) for obligation in ("repository-readiness", "environment-reproducibility", "toolchain-identity")),
        now=NOW,
    )
    assert unsigned.readiness is ReadinessState.BLOCKED
    evaluator = CertificationEvaluator(verifier=TestClaimVerifier())
    local_claims = tuple(claim(CertificationLevel.E0, obligation) for obligation in ("repository-readiness", "environment-reproducibility", "toolchain-identity"))
    local = evaluator.evaluate(project_id="project-a", job_id="job-a", source_revision=sha("source"), target_revision=sha("target"), target_level=CertificationLevel.E0, claims=local_claims, now=NOW)
    assert local.bundle.verdict is CertificationVerdict.INSUFFICIENT_EVIDENCE
    assert local.readiness is ReadinessState.READY_FOR_EXTERNAL_GATE
    assert local.certification_status == "NOT_CERTIFIED"
    assert local.external_evidence_complete is False
    untrusted = tuple(claim(CertificationLevel.E0, obligation, independent=False, evidence_id=f"untrusted-{obligation}") for obligation in ("repository-readiness", "environment-reproducibility", "toolchain-identity"))
    missing_independent = evaluator.evaluate(project_id="project-a", job_id="job-a", source_revision=sha("source"), target_revision=sha("target"), target_level=CertificationLevel.E0, claims=untrusted, now=NOW)
    assert missing_independent.readiness is ReadinessState.BLOCKED
    assert missing_independent.bundle.gates["E0"].value == "INSUFFICIENT_EVIDENCE"
    for label, produced_at in (("old", NOW - timedelta(days=31)), ("future", NOW + timedelta(minutes=6))):
        stale = tuple(
            claim(CertificationLevel.E0, obligation, external=True, evidence_id=f"{label}-{obligation}", produced_at=produced_at)
            for obligation in ("repository-readiness", "environment-reproducibility", "toolchain-identity")
        )
        stale_decision = evaluator.evaluate(project_id="project-a", job_id="job-a", source_revision=sha("source"), target_revision=sha("target"), target_level=CertificationLevel.E0, claims=stale, now=NOW)
        assert stale_decision.readiness is ReadinessState.BLOCKED
        assert stale_decision.bundle.gates["E0"].value == "INSUFFICIENT_EVIDENCE"
    external_claims = tuple(claim(CertificationLevel.E0, obligation, external=True, evidence_id=f"external-{obligation}") for obligation in ("repository-readiness", "environment-reproducibility", "toolchain-identity"))
    for severity in (FindingSeverity.P0, FindingSeverity.P1):
        blocked = evaluator.evaluate(project_id="project-a", job_id="job-a", source_revision=sha("source"), target_revision=sha("target"), target_level=CertificationLevel.E0, claims=external_claims, findings=(Finding(f"finding-{severity.value}", severity, "open issue", ("external-repository-readiness",)),), now=NOW)
        assert blocked.bundle.verdict is CertificationVerdict.FAIL
        assert blocked.readiness is ReadinessState.BLOCKED
