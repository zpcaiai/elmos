from __future__ import annotations

from datetime import UTC, datetime, timedelta
import pytest

from elmos_pdhi.agent_runtime import (
    AgentAuthorizationError,
    AgentCapability,
    AgentDefinition,
    AgentDefinitionRegistry,
    AgentEffectKind,
    AgentState,
    AgentSupervisor,
    AgentTaskDAG,
    EffortLevel,
    EffectStatus,
    InMemoryAgentTaskStateStore,
    InMemoryWorkspaceAuthority,
    K4_CAPABILITIES,
    K4_OPERATION_BINDINGS,
    K4_OPERATION_SPECS,
    ModelPolicy,
    SchedulingMode,
    SecurityCeiling,
    SpawnGuard,
    SpawnPolicy,
    SpawnRequest,
    StaleFenceError,
    TypedAgentYield,
    YieldValidator,
    resolve_k4_binding,
)
from elmos_pdhi.assurance import (
    AdvisorBacklog,
    AdvisorStatus,
    CredentialVerificationReceipt,
    K5_CAPABILITIES,
    K5_OPERATION_BINDINGS,
    IndependentAdvisorRuntime,
    ReleaseReviewDecision,
    ReviewEvidencePath,
    ReviewVote,
    ReviewerConsensus,
    ReviewerCredential,
    ReviewerPrincipal,
    ReviewerVerdict,
    WatchdogKind,
)
from elmos_pdhi.canonical import digest_object
from elmos_pdhi.contracts import (
    AgentResultStatus,
    AgentTask,
    AuthorityLevel,
    EvidenceRecord,
    EvidenceStatus,
    ExecutionContext,
    ProofCarryingAgentResult,
    ResourceScope,
    RuleEnforcement,
    RuleIR,
    VerificationStatus,
)
from elmos_pdhi.errors import (
    AuthorizationError,
    ConflictError,
    UnknownCapabilityError,
    ValidationError,
)
from elmos_pdhi.policy import (
    InMemoryPolicyAuditStore,
    K6_CAPABILITIES,
    K6_OPERATION_BINDINGS,
    PDPDecision,
    PolicyDecisionPoint,
    PolicyEnforcementPoint,
    PolicyEvaluationContext,
    RuleNormalizer,
    RuleSource,
    resolve_k6_binding,
)


NOW = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)


def scope(
    *,
    tenant: str = "tenant-a",
    project: str = "project-a",
    repository: str = "repo-a",
    write: bool = False,
) -> ResourceScope:
    return ResourceScope(
        tenant_id=tenant,
        project_id=project,
        repository_id=repository,
        input_revision="revision-1",
        read_scope=(".",),
        write_scope=("src",) if write else (),
    )


def context(
    resource_scope: ResourceScope,
    *,
    actor: str = "actor-a",
    task: str = "task-a",
    workspace: str = "workspace-a",
    lease: str = "lease-1",
    fence: int = 1,
) -> ExecutionContext:
    writable = bool(resource_scope.write_scope)
    return ExecutionContext(
        scope=resource_scope,
        actor_id=actor,
        job_id="job-a",
        task_id=task,
        authority_profile="profile-a",
        idempotency_key=f"idem-{task}-{fence}",
        workspace_id=workspace if writable else None,
        lease_id=lease if writable else None,
        fence_token=fence if writable else None,
    )


def evidence(
    resource_scope: ResourceScope,
    *,
    evidence_id: str = "evidence-1",
    producer: str = "tool-principal",
    status: EvidenceStatus = EvidenceStatus.VALID,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type="compiler",
        producer=producer,
        produced_at=NOW,
        input_digests=(digest_object({"input": evidence_id}, domain="test-input"),),
        artifact_digest=digest_object({"artifact": evidence_id}, domain="test-artifact"),
        tool_version="compiler-1",
        scope=resource_scope,
        status=status,
    )


def result(*, evidence_id: str = "evidence-1") -> ProofCarryingAgentResult:
    return ProofCarryingAgentResult(
        task_id="task-a",
        status=AgentResultStatus.SUCCEEDED,
        changed_artifacts=("src/changed.py",),
        evidence=(evidence_id,),
        findings=(),
        unresolved=(),
        verification_status=VerificationStatus.PASS,
    )


def reviewer(
    resource_scope: ResourceScope,
    *,
    principal_id: str = "reviewer-1",
    independence_domain: str = "review-org",
) -> ReviewerPrincipal:
    credential = ReviewerCredential(
        credential_id=f"credential-{principal_id}",
        subject_principal_id=principal_id,
        issuer_principal_id="credential-authority",
        credential_digest=digest_object({"credential": principal_id}, domain="test-credential"),
        tenant_id=resource_scope.tenant_id,
        project_id=resource_scope.project_id,
        repository_id=resource_scope.repository_id,
        allowed_evidence_types=("compiler",),
        issued_at=NOW - timedelta(minutes=5),
        expires_at=NOW + timedelta(hours=1),
        independently_verified=True,
    )
    return ReviewerPrincipal(principal_id, independence_domain, ("release-reviewer",), credential)


def review_path(
    resource_scope: ResourceScope,
    *,
    reviewer_principal: ReviewerPrincipal | None = None,
    record: EvidenceRecord | None = None,
    executor: str = "executor-1",
    executor_domain: str = "executor-org",
) -> ReviewEvidencePath:
    selected = reviewer_principal or reviewer(resource_scope)
    receipt = CredentialVerificationReceipt(
        verification_id=f"verification-{selected.principal_id}",
        credential_id=selected.credential.credential_id,
        credential_digest=selected.credential.credential_digest,
        subject_principal_id=selected.principal_id,
        verifier_principal_id="credential-verifier",
        verifier_independence_domain="credential-authority-domain",
        scope=resource_scope,
        evidence_digest=digest_object(
            {"credential": selected.credential.credential_id},
            domain="test-credential-verification",
        ),
        verified_at=NOW - timedelta(minutes=4),
        expires_at=NOW + timedelta(minutes=30),
    )
    return ReviewEvidencePath(
        path_id=f"path-{selected.principal_id}",
        scope=resource_scope,
        executor_principal_id=executor,
        executor_independence_domain=executor_domain,
        reviewer=selected,
        evidence=(record or evidence(resource_scope),),
        credential_verification=receipt,
    )


def test_exact_k4_k6_bindings_and_canonical_duplicate_owner() -> None:
    assert len(K4_CAPABILITIES) == len(K4_OPERATION_BINDINGS) == 30
    assert len(K5_CAPABILITIES) == len(K5_OPERATION_BINDINGS) == 28
    assert len(K6_CAPABILITIES) == len(K6_OPERATION_BINDINGS) == 24
    phase = K4_OPERATION_BINDINGS["phase-model-handoff"]
    assert phase.source_owner == "K4"
    assert phase.canonical_owner == "K8"
    assert K4_OPERATION_SPECS["phase-model-handoff"].canonical_owner == "K8"
    assert "K4" in K4_OPERATION_SPECS["phase-model-handoff"].occurrence_owners
    with pytest.raises(UnknownCapabilityError):
        resolve_k4_binding("not-a-real-operation")
    with pytest.raises(UnknownCapabilityError):
        resolve_k6_binding("not-a-real-operation")


def test_workspace_scope_isolation_and_stale_fence_rejection() -> None:
    resource_scope = scope(write=True)
    first = context(resource_scope)
    authority = InMemoryWorkspaceAuthority()
    authority.claim_owner(first, agent_id="agent-a", now=NOW)
    authority.issue_lease(first, agent_id="agent-a", ttl=timedelta(minutes=15), now=NOW)
    assert authority.validate(first, agent_id="agent-a", now=NOW).fence_token == 1

    cross_tenant = context(scope(tenant="tenant-b", write=True))
    with pytest.raises(AuthorizationError) as isolation:
        authority.validate(cross_tenant, agent_id="agent-a", now=NOW)
    assert isolation.value.code == "WORKSPACE_AUTHORITY_MISSING"

    renewed = context(resource_scope, lease="lease-2", fence=2)
    authority.issue_lease(renewed, agent_id="agent-a", ttl=timedelta(minutes=15), now=NOW)
    with pytest.raises(StaleFenceError) as stale:
        authority.validate(first, agent_id="agent-a", now=NOW)
    assert stale.value.code in {"STALE_LEASE", "STALE_FENCE"}


def test_agent_task_dag_is_versioned_and_persisted() -> None:
    resource_scope = scope()
    store = InMemoryAgentTaskStateStore()
    dag = AgentTaskDAG(resource_scope, "job-a", store)
    task = AgentTask(
        task_id="task-a",
        project_id="project-a",
        job_id="job-a",
        goal="perform bounded analysis",
        input_revision="revision-1",
        read_scope=(".",),
        write_scope=(),
        authority_profile="profile-a",
        output_schema={"type": "object"},
        invariants=("tenant isolation",),
    )
    node = dag.add(task, now=NOW)
    ready = dag.transition("task-a", AgentState.READY, expected_version=node.version, now=NOW)
    running = dag.transition("task-a", AgentState.RUNNING, expected_version=ready.version, now=NOW)
    dag.transition(
        "task-a",
        AgentState.SUCCEEDED,
        expected_version=running.version,
        now=NOW,
        completed_effect_id="effect-1",
    )
    restored = AgentTaskDAG(resource_scope, "job-a", store)
    assert restored.nodes["task-a"].state is AgentState.SUCCEEDED
    assert restored.nodes["task-a"].completed_effect_ids == ("effect-1",)


def test_agent_task_dag_rejects_stale_concurrent_writer() -> None:
    resource_scope = scope()
    store = InMemoryAgentTaskStateStore()
    first = AgentTaskDAG(resource_scope, "job-a", store)
    stale = AgentTaskDAG(resource_scope, "job-a", store)

    def task(task_id: str) -> AgentTask:
        return AgentTask(
            task_id=task_id,
            project_id="project-a",
            job_id="job-a",
            goal=f"bounded task {task_id}",
            input_revision="revision-1",
            read_scope=(".",),
            write_scope=(),
            authority_profile="profile-a",
            output_schema={"type": "object"},
            invariants=("tenant isolation",),
        )

    first.add(task("task-first"), now=NOW)
    with pytest.raises(ConflictError) as conflict:
        stale.add(task("task-stale"), now=NOW)
    assert getattr(conflict.value, "code", None) == "STALE_TASK_GRAPH"


def test_spawn_policy_rejects_unauthorized_agent_and_effect_is_not_run() -> None:
    registry = AgentDefinitionRegistry()
    registry.register_capability(
        AgentCapability("read-source", ("read",), security_ceiling=SecurityCeiling.REPOSITORY_READ)
    )
    registry.register_definition(
        AgentDefinition(
            agent_id="child-agent",
            namespace="project",
            name="reader",
            version="1.0.0",
            capability_ids=("read-source",),
            authority_profile="profile-a",
            model_policy=ModelPolicy(
                ("model-a",), EffortLevel.HIGH, SecurityCeiling.REPOSITORY_READ
            ),
            max_depth=2,
        )
    )
    request = SpawnRequest(
        context=context(scope()),
        parent_agent_id="parent-agent",
        namespace="project",
        name="reader",
        version="1.0.0",
        capability_id="read-source",
        model_candidates=("model-a",),
        effort=EffortLevel.MEDIUM,
        security=SecurityCeiling.REPOSITORY_READ,
        depth=1,
        lineage=("parent-agent",),
        scheduling=SchedulingMode.ASYNC,
    )
    guard = SpawnGuard(registry, InMemoryWorkspaceAuthority())
    denied = SpawnPolicy(
        allowed_parent_agent_ids=frozenset({"parent-agent"}),
        allowed_agent_ids=frozenset(),
        allowed_capability_ids=frozenset({"read-source"}),
        maximum_depth=2,
        effort_ceiling=EffortLevel.HIGH,
        security_ceiling=SecurityCeiling.REPOSITORY_READ,
    )
    with pytest.raises(AgentAuthorizationError) as unauthorized:
        guard.authorize(request, denied, now=NOW)
    assert unauthorized.value.code == "UNAUTHORIZED_SPAWN"

    allowed = SpawnPolicy(
        allowed_parent_agent_ids=frozenset({"parent-agent"}),
        allowed_agent_ids=frozenset({"child-agent"}),
        allowed_capability_ids=frozenset({"read-source"}),
        maximum_depth=2,
        effort_ceiling=EffortLevel.HIGH,
        security_ceiling=SecurityCeiling.REPOSITORY_READ,
    )
    effect = guard.authorize(request, allowed, now=NOW)
    assert effect.kind is AgentEffectKind.SPAWN
    assert effect.status is EffectStatus.NOT_RUN
    assert effect.external_evidence_status is EffectStatus.NOT_RUN


def test_malformed_and_unknown_evidence_agent_yields_are_rejected() -> None:
    resource_scope = scope(write=True)
    expected = context(resource_scope, actor="child-agent")
    validator = YieldValidator()
    with pytest.raises(ValidationError) as malformed:
        validator.validate({"task_id": "task-a"}, expected_context=expected)  # type: ignore[arg-type]
    assert malformed.value.code == "MALFORMED_AGENT_YIELD"

    not_run = evidence(resource_scope, status=EvidenceStatus.NOT_RUN)
    yielded = TypedAgentYield(
        context=expected,
        agent_id="child-agent",
        parent_task_id="parent-task",
        result=result(),
        evidence_records=(not_run,),
        workspace_snapshot_id="snapshot-1",
    )
    with pytest.raises(ValidationError) as unknown:
        validator.validate(yielded, expected_context=expected)
    assert unknown.value.code == "UNKNOWN_YIELD_EVIDENCE"


def test_supervisor_control_and_merge_side_effects_remain_not_run() -> None:
    resource_scope = scope(write=True)
    execution = context(resource_scope)
    authority = InMemoryWorkspaceAuthority()
    authority.claim_owner(execution, agent_id="agent-a", now=NOW)
    authority.issue_lease(execution, agent_id="agent-a", ttl=timedelta(minutes=15), now=NOW)
    supervisor = AgentSupervisor(authority, YieldValidator())
    park = supervisor.request_park(execution, agent_id="agent-a", checkpoint_id="checkpoint-1", now=NOW)
    kill = supervisor.request_kill(execution, agent_id="agent-a", reason="operator request")
    assert {park.kind, kill.kind} == {AgentEffectKind.PARK, AgentEffectKind.KILL}
    assert park.status is kill.status is EffectStatus.NOT_RUN


def test_merge_gate_requires_persisted_current_snapshot_and_independent_pass() -> None:
    resource_scope = scope(write=True)
    execution = context(resource_scope, actor="agent-a")
    authority = InMemoryWorkspaceAuthority()
    authority.claim_owner(execution, agent_id="agent-a", now=NOW)
    authority.issue_lease(execution, agent_id="agent-a", ttl=timedelta(minutes=15), now=NOW)
    snapshot = authority.create_snapshot(
        execution,
        agent_id="agent-a",
        revision_digest=digest_object({"tree": "after"}, domain="test-tree"),
        now=NOW,
    )
    typed_yield = TypedAgentYield(
        context=execution,
        agent_id="agent-a",
        parent_task_id="parent-task",
        result=result(),
        evidence_records=(evidence(resource_scope),),
        workspace_snapshot_id=snapshot.snapshot_id,
    )
    independent_pass = ReleaseReviewDecision(
        ReviewerVerdict.PASS, (), ("path-1",), True, "independent reviewers agree"
    )
    supervisor = AgentSupervisor(authority, YieldValidator())
    merge = supervisor.request_merge(
        execution,
        agent_id="agent-a",
        yielded=typed_yield,
        snapshot=snapshot,
        independent_review_status=independent_pass,
        now=NOW,
    )
    assert merge.kind is AgentEffectKind.MERGE
    assert merge.status is EffectStatus.NOT_RUN

    renewed = context(resource_scope, actor="agent-a", lease="lease-2", fence=2)
    authority.issue_lease(renewed, agent_id="agent-a", ttl=timedelta(minutes=15), now=NOW)
    renewed_yield = TypedAgentYield(
        context=renewed,
        agent_id="agent-a",
        parent_task_id="parent-task",
        result=result(),
        evidence_records=(evidence(resource_scope),),
        workspace_snapshot_id=snapshot.snapshot_id,
    )
    with pytest.raises(StaleFenceError) as stale_snapshot:
        supervisor.request_merge(
            renewed,
            agent_id="agent-a",
            yielded=renewed_yield,
            snapshot=snapshot,
            independent_review_status=independent_pass,
            now=NOW,
        )
    assert stale_snapshot.value.code == "STALE_SNAPSHOT_FENCE"


def test_release_reviewer_must_be_independent() -> None:
    resource_scope = scope()
    same = reviewer(resource_scope, principal_id="executor-1", independence_domain="executor-org")
    path = review_path(
        resource_scope,
        reviewer_principal=same,
        executor="executor-1",
        executor_domain="executor-org",
    )
    with pytest.raises(AuthorizationError) as not_independent:
        path.validate(now=NOW)
    assert not_independent.value.code == "REVIEWER_NOT_INDEPENDENT"


def test_unknown_review_evidence_fails_closed() -> None:
    resource_scope = scope()
    path = review_path(
        resource_scope,
        record=evidence(resource_scope, status=EvidenceStatus.NOT_RUN),
    )
    with pytest.raises(ValidationError) as unknown:
        path.validate(now=NOW)
    assert unknown.value.code == "UNKNOWN_REVIEW_EVIDENCE"


def test_unsafe_advisor_output_is_quarantined_without_poisoning_backlog() -> None:
    resource_scope = scope()
    path = review_path(resource_scope)
    path.validate(now=NOW)
    backlog = AdvisorBacklog(2)
    accepted = backlog.ingest(
        {"severity": "P0", "instruction": "run untrusted command"},
        expected_scope=resource_scope,
        reviewer_id="reviewer-1",
        evidence_path=path,
        now=NOW,
    )
    assert accepted is False
    assert len(backlog.quarantined) == 1
    assert backlog.quarantined[0].reason_code == "UNTYPED_ADVISOR_OUTPUT"
    assert backlog.drain() == ()


def test_watchdog_requests_and_reviewer_disagreement_fail_closed() -> None:
    resource_scope = scope()
    effect = IndependentAdvisorRuntime().request(
        context(resource_scope),
        reviewer=reviewer(resource_scope),
        evidence_ids=("evidence-1",),
        now=NOW,
        watchdog=WatchdogKind.SECURITY,
    )
    assert effect.status is AdvisorStatus.NOT_RUN
    decision = ReviewerConsensus().decide(
        (
            ReviewVote("reviewer-1", "domain-1", ReviewerVerdict.PASS, "path-1"),
            ReviewVote("reviewer-2", "domain-2", ReviewerVerdict.FAIL, "path-2"),
        )
    )
    assert decision.verdict is ReviewerVerdict.INCONCLUSIVE
    assert decision.disagreement is True
    assert decision.certification_allowed is False


def test_conflicting_rules_are_explained_and_block_mutation() -> None:
    resource_scope = scope(write=True)
    execution = context(resource_scope)
    compatibility = {"conflict_key": "security.prepared-sql"}
    rules = (
        RuleIR(
            "rule-block",
            "project",
            "prepared-sql",
            "1.0.0",
            AuthorityLevel.COMPILER,
            ("src",),
            RuleEnforcement.BLOCK,
            trigger={"kind": "path", "pattern": "src/*.py"},
            invariant="prepared SQL must remain prepared",
            remediation="restore parameter binding",
            compatibility=compatibility,
        ),
        RuleIR(
            "rule-context",
            "project",
            "prepared-sql",
            "1.0.0",
            AuthorityLevel.COMPILER,
            ("src",),
            RuleEnforcement.CONTEXT,
            trigger={"kind": "path", "pattern": "src/*.py"},
            invariant="prepared SQL should remain prepared",
            compatibility=compatibility,
        ),
    )
    pdp = PolicyDecisionPoint(resource_scope, rules)
    decision = pdp.evaluate(
        PolicyEvaluationContext(execution, path="src/query.py", mutation=True)
    )
    assert decision.decision is PDPDecision.INDETERMINATE
    assert len(decision.conflicts) == 1
    assert decision.conflicts[0].resolved is False
    assert "explicit override" in decision.conflicts[0].explanation
    audit = InMemoryPolicyAuditStore()
    enforced = PolicyEnforcementPoint(audit).enforce(
        execution, decision, mutation=True, now=NOW
    )
    assert enforced.allowed is False
    assert enforced.violations
    assert audit.list_for_scope(resource_scope)


def test_unknown_invariant_evidence_and_unmatched_mutation_fail_closed() -> None:
    resource_scope = scope(write=True)
    execution = context(resource_scope)
    rule = RuleIR(
        "rule-proof",
        "project",
        "proof-required",
        "1.0.0",
        AuthorityLevel.SEMANTIC_IR,
        ("src",),
        RuleEnforcement.CONTEXT,
        trigger={"kind": "always"},
        invariant="semantic proof evidence is required",
        evidence_requirement=("semantic-proof",),
    )
    pdp = PolicyDecisionPoint(resource_scope, (rule,))
    unknown = pdp.evaluate(
        PolicyEvaluationContext(
            execution,
            path="src/main.py",
            evidence_records={
                "semantic-proof": evidence(
                    resource_scope,
                    evidence_id="semantic-proof",
                    status=EvidenceStatus.NOT_RUN,
                )
            },
            mutation=True,
        )
    )
    assert unknown.decision is PDPDecision.INDETERMINATE
    enforced = PolicyEnforcementPoint(InMemoryPolicyAuditStore()).enforce(
        execution, unknown, mutation=True, now=NOW
    )
    assert enforced.allowed is False
    assert enforced.violations[0].required_evidence == ("semantic-proof",)

    unmatched = PolicyDecisionPoint(resource_scope, ()).evaluate(
        PolicyEvaluationContext(execution, path="src/main.py", mutation=True)
    )
    default_denied = PolicyEnforcementPoint(InMemoryPolicyAuditStore()).enforce(
        execution, unmatched, mutation=True, now=NOW
    )
    assert default_denied.allowed is False
    assert default_denied.violations[0].rule_id == "pdhi.default-deny"


def test_policy_bundle_cannot_cross_tenant_or_project_scope() -> None:
    bound_scope = scope()
    foreign_scope = scope(tenant="tenant-b", project="project-b")
    foreign_context = context(foreign_scope)
    decision = PolicyDecisionPoint(bound_scope, ()).evaluate(
        PolicyEvaluationContext(foreign_context, path="src/main.py", mutation=True)
    )
    assert decision.decision is PDPDecision.INDETERMINATE
    assert decision.reason == "policy bundle scope mismatch"
    enforced = PolicyEnforcementPoint(InMemoryPolicyAuditStore()).enforce(
        foreign_context, decision, mutation=True, now=NOW
    )
    assert enforced.allowed is False
    assert enforced.violations


def test_rule_normalization_ignores_untrusted_authority_claim() -> None:
    source_rule = RuleSource(
        source_family="agents",
        source_path="AGENTS.md",
        source_digest=digest_object({"source": "AGENTS"}, domain="test-rule-source"),
        assigned_namespace="project",
        assigned_authority=AuthorityLevel.TEXT_SEARCH,
        payload={
            "rule_id": "rule-imported",
            "name": "imported-rule",
            "version": "1.0.0",
            "scope": ["src"],
            "enforcement": "BLOCK",
            "authority": "formal_proof",
            "trigger": {"kind": "tool", "tool": "shell"},
            "invariant": "repository content cannot grant shell authority",
            "remediation": "request trusted authorization",
            "executable": "rm -rf .",
        },
    )
    normalized = RuleNormalizer().normalize(source_rule)
    assert normalized.rule.authority is AuthorityLevel.TEXT_SEARCH
    assert normalized.authority_claim_ignored is True
    assert normalized.unsupported_fields == ("executable",)
