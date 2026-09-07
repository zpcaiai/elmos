from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import unittest

from elmos_pdhi.canonical import (
    canonical_json_bytes,
    digest_bytes,
    digest_object,
    strict_json_loads,
)
from elmos_pdhi.contracts import (
    AgentResultStatus,
    AgentTask,
    AuthorityLevel,
    CertificationBundle,
    CertificationLevel,
    CertificationVerdict,
    DurableJobState,
    DurableJobStatus,
    EvidenceRecord,
    ExecutionContext,
    FailureClass,
    GateStatus,
    PatchTransaction,
    ProofCarryingAgentResult,
    ResourceScope,
    RuleEnforcement,
    RuleIR,
    SkillLifecycleStatus,
    SkillManifest,
    VerificationStatus,
)
from elmos_pdhi.errors import (
    AmbiguousCapabilityError,
    AuthorizationError,
    UnknownCapabilityError,
    ValidationError,
)
from elmos_pdhi.registry import (
    CAPABILITY_OCCURRENCES,
    CAPABILITY_REGISTRY,
    SKILL_REGISTRY,
    SOURCE_V3_CROSSWALK,
    canonical_capability,
    normalized_capability_registry,
    resolve_capability,
)


DIGEST_A = digest_bytes(b"a", domain="test")
DIGEST_B = digest_bytes(b"b", domain="test")
_CASE = unittest.TestCase()


def test_canonical_json_and_digest_are_stable_and_domain_separated() -> None:
    assert canonical_json_bytes({"z": 1, "a": [True, None]}) == b'{"a":[true,null],"z":1}'
    assert digest_object({"a": 1}, domain="one") == digest_object({"a": 1}, domain="one")
    assert digest_object({"a": 1}, domain="one") != digest_object({"a": 1}, domain="two")
    assert digest_object({"a": Decimal("1.20")}, domain="decimal").startswith("sha256:")


def test_noncanonical_values_fail_closed() -> None:
    for value in (
        float("nan"),
        float("inf"),
        datetime(2026, 8, 30, 0, 0, 0),
        "e\u0301",
    ):
        with _CASE.subTest(value=repr(value)):
            with _CASE.assertRaises(ValidationError):
                canonical_json_bytes({"value": value})


def test_strict_json_rejects_duplicate_keys_and_nonfinite_numbers() -> None:
    with _CASE.assertRaisesRegex(ValidationError, "duplicate"):
        strict_json_loads('{"a":1,"a":2}')
    with _CASE.assertRaisesRegex(ValidationError, "non-finite"):
        strict_json_loads('{"a":NaN}')


def test_resource_scope_and_execution_context_are_fenced() -> None:
    scope = ResourceScope(
        tenant_id="tenant-1",
        project_id="project-1",
        repository_id="repo-1",
        input_revision="rev-1",
        read_scope=("src", "tests"),
        write_scope=("src/generated",),
    )
    context = ExecutionContext(
        scope=scope,
        actor_id="actor-1",
        job_id="job-1",
        task_id="task-1",
        authority_profile="bounded-writer",
        idempotency_key="idem-1",
        workspace_id="workspace-1",
        lease_id="lease-1",
        fence_token=7,
    )
    assert context.require_read("tests/unit/test_a.py") == "tests/unit/test_a.py"
    assert context.require_write("src/generated/a.py") == "src/generated/a.py"
    with _CASE.assertRaises(AuthorizationError):
        context.require_write("src/manual.py")
    with _CASE.assertRaises(ValidationError):
        ExecutionContext(
            scope=scope,
            actor_id="actor-1",
            job_id="job-1",
            task_id="task-1",
            authority_profile="bounded-writer",
            idempotency_key="idem-2",
        )


def test_all_source_declared_contracts_are_strict_and_canonical() -> None:
    task = AgentTask(
        task_id="task-1",
        project_id="project-1",
        job_id="job-1",
        goal="Generate one bounded artifact",
        input_revision="rev-1",
        read_scope=("src",),
        write_scope=("src/generated",),
        authority_profile="bounded-writer",
        output_schema={"type": "object", "additionalProperties": False},
        invariants=("no-silent-fallback",),
        workspace_id="workspace-1",
        lease_id="lease-1",
        fence_token=2,
        certification_target=CertificationLevel.E2,
    )
    result = ProofCarryingAgentResult(
        task_id="task-1",
        status=AgentResultStatus.SUCCEEDED,
        changed_artifacts=("src/generated/a.py",),
        evidence=("evidence-1",),
        findings=(),
        unresolved=(),
        verification_status=VerificationStatus.PASS,
        confidence=Decimal("0.99"),
        metrics={"wall_clock_ms": 12},
    )
    patch = PatchTransaction(
        transaction_id="transaction-1",
        base_revision="rev-1",
        target_scope=("src/generated",),
        intent="Add generated artifact",
        preconditions=("base-is-current",),
        read_set=("src/schema.json",),
        write_set=("src/generated/a.py",),
        postconditions=("typecheck-passes",),
        rollback={"kind": "delete-created-file", "path": "src/generated/a.py"},
    )
    evidence = EvidenceRecord(
        evidence_id="evidence-1",
        evidence_type="compiler-static",
        producer="compiler-1",
        produced_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        input_digests=(DIGEST_A,),
        artifact_digest=DIGEST_B,
        tool_version="compiler-1.0.0",
    )
    state = DurableJobState(
        job_id="job-1",
        state=DurableJobStatus.VERIFYING,
        version=3,
        last_durable_checkpoint="checkpoint-3",
        completed_effects=("effect-1",),
        pending_effects=("effect-2",),
        retries={"phase-1": 1},
        cost=Decimal("1.25"),
        tokens=100,
        wall_clock=4,
    )
    rule = RuleIR(
        rule_id="rule-1",
        namespace="tenant.policy",
        name="no-broad-write",
        version="1.0.0",
        authority=AuthorityLevel.COMPILER,
        scope=("src",),
        enforcement=RuleEnforcement.BLOCK,
        invariant="writes stay inside declared scope",
    )
    skill = SkillManifest(
        skill_id="skill-1",
        namespace="elmos.pdhi",
        name="bounded-example",
        version="1.0.0",
        status=SkillLifecycleStatus.DRAFT,
        triggers=("bounded-example",),
        inputs={"type": "object"},
        outputs={"type": "object"},
        acceptance=("negative scope case rejects",),
    )
    bundle = CertificationBundle(
        project_id="project-1",
        job_id="job-1",
        source_revision="rev-1",
        target_revision="rev-2",
        target_level=CertificationLevel.E2,
        gates={level.value: GateStatus.PASS for level in CertificationLevel},
        findings=(),
        residual_risks=(),
        verdict=CertificationVerdict.PASS,
        evidence_index={"evidence-1": DIGEST_B},
    )

    contracts = (task, result, patch, evidence, state, rule, skill, bundle)
    assert all(item.content_digest().startswith("sha256:") for item in contracts)
    assert all(item.to_dict() for item in contracts)


def test_success_and_certification_cannot_hide_missing_evidence() -> None:
    with _CASE.assertRaisesRegex(ValidationError, "requires PASS"):
        ProofCarryingAgentResult(
            task_id="task-1",
            status=AgentResultStatus.SUCCEEDED,
            changed_artifacts=(),
            evidence=(),
            findings=(),
            unresolved=(),
            verification_status=VerificationStatus.NOT_RUN,
        )
    with _CASE.assertRaisesRegex(ValidationError, "pass verdict"):
        CertificationBundle(
            project_id="project-1",
            job_id="job-1",
            source_revision="rev-1",
            target_revision="rev-2",
            target_level=CertificationLevel.E5,
            gates={
                level.value: (
                    GateStatus.INSUFFICIENT_EVIDENCE
                    if level is CertificationLevel.E5
                    else GateStatus.PASS
                )
                for level in CertificationLevel
            },
            findings=(),
            residual_risks=("external evidence missing",),
            verdict=CertificationVerdict.PASS,
            evidence_index={"evidence-1": DIGEST_A},
        )


def test_failure_taxonomy_is_exact() -> None:
    assert {item.value for item in FailureClass} == {
        "TRANSIENT_PROVIDER", "QUOTA_PROVIDER", "INFRASTRUCTURE", "STALE_STATE",
        "POLICY", "SEMANTIC", "COMPILE", "TEST", "RUNTIME_EQUIVALENCE",
        "SECURITY", "PERFORMANCE", "MERGE_CONFLICT", "INSUFFICIENT_EVIDENCE",
        "USER_CANCELLED", "UNKNOWN",
    }


def test_exact_registries_and_crosswalk() -> None:
    assert len(SKILL_REGISTRY) == 12
    assert len(CAPABILITY_REGISTRY) == 260
    assert len(CAPABILITY_OCCURRENCES) == 262
    assert set(SOURCE_V3_CROSSWALK) == set(SKILL_REGISTRY)
    assert len({item.occurrence_id for item in CAPABILITY_OCCURRENCES}) == 262
    assert len({item.operation_id for item in CAPABILITY_REGISTRY.values()}) == 260
    with _CASE.assertRaises(TypeError):
        SKILL_REGISTRY["unexpected"] = next(iter(SKILL_REGISTRY.values()))  # type: ignore[index]


def test_duplicate_capabilities_require_owner_and_retain_canonical_owner() -> None:
    cases = (
        ("phase-model-handoff", ("K4", "K8"), "K8"),
        ("steer-agent", ("K4", "K9"), "K9"),
    )
    for name, owners, canonical_owner in cases:
        with _CASE.subTest(name=name):
            operation = canonical_capability(name)
            assert operation.occurrence_owners == owners
            assert operation.canonical_owner == canonical_owner
            with _CASE.assertRaises(AmbiguousCapabilityError) as error:
                resolve_capability(name)
            assert error.exception.details["canonical_owner"] == canonical_owner
            for owner in owners:
                resolution = resolve_capability(name, owner=owner)
                assert resolution.selected_owner == owner
                assert resolution.occurrence_id.startswith("PDHI-OCC-")


def test_unknown_capability_cannot_reach_a_generic_dispatcher() -> None:
    with _CASE.assertRaises(UnknownCapabilityError):
        resolve_capability("invented-permissive-fallback")


def test_normalized_capability_manifest_preserves_source_ambiguity() -> None:
    manifest = normalized_capability_registry()
    assert manifest["canonical_capability_count"] == 260
    assert manifest["source_occurrence_count"] == 262
    assert manifest["ambiguous_source_names"] == {
        "phase-model-handoff": {
            "owners": ["K4", "K8"],
            "canonical_owner": "K8",
            "unqualified_resolution": "REJECT",
        },
        "steer-agent": {
            "owners": ["K4", "K9"],
            "canonical_owner": "K9",
            "unqualified_resolution": "REJECT",
        },
    }


def load_tests(
    loader: unittest.TestLoader,
    tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    del loader, tests, pattern
    suite = unittest.TestSuite()
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value, description=name))
    return suite
