"""Industrial-grade test suite for v3.2 Engineering Control Plane & Durable Harness Delta.

Tests all 12 Batches (B01-B12) and 20 Normative Invariants from docs/INVARIANTS.md.
"""

from datetime import UTC, datetime, timedelta
import hashlib
import unittest

from elmos_proof_harness.delta_v32 import (
    ApprovalActionKind,
    ApprovalBinding,
    ApprovalDecision,
    ArtifactConflictError,
    AuthorityViolationError,
    CapabilityInventory,
    ContextEnvelope,
    ContextScope,
    ContextTrust,
    EngineeringObserver,
    EnvironmentFingerprint,
    ExecutionSource,
    ExecutionSourceKind,
    ExecutionTimeline,
    ExecutionTimelineEvent,
    HandoffProtocol,
    InterruptLifecycle,
    InvalidOwnershipTransitionError,
    Negotiation,
    OwnerRecord,
    OwnershipState,
    PathKind,
    PeerBinding,
    Policy,
    PreparedWorkerPool,
    PublicationAction,
    PublicationBroker,
    PublicationDeniedError,
    PublicationRequest,
    PublicationRequestStatus,
    ReleaseEvidenceManifest,
    ReleaseVerificationCheck,
    RepositoryCheckpoint,
    RepositoryCheckpointEntry,
    ResultFence,
    ResultFenceState,
    RuntimeConnectionState,
    RuntimeOwner,
    RuntimeState,
    RuntimeStatusObserver,
    SessionInheritancePolicy,
    SessionRole,
    SideEffectReceipt,
    SideEffectStatus,
    StaleOwnerEpochError,
    ToolCallJournal,
    ToolTerminalStatus,
    TypedArtifact,
    TypedArtifactStore,
    VerificationStatus,
    approval_matches,
    compact_context,
    intersect_policies,
    monotonic_authority,
    negotiate,
    release_gate,
)


class TestBatch01IdentityAndOwnership(unittest.TestCase):
    """Batch 01: Core execution identity and ownership invariants."""

    def test_execution_source_root_and_child(self) -> None:
        root_source = ExecutionSource(
            source=ExecutionSourceKind.ROOT_AGENT,
            root_execution_id="exec-root-001",
            producer="orchestrator",
        )
        self.assertTrue(root_source.is_root)
        self.assertEqual(root_source.source, ExecutionSourceKind.ROOT_AGENT)

        child_source = ExecutionSource(
            source=ExecutionSourceKind.SUBAGENT,
            root_execution_id="exec-root-001",
            parent_execution_id="exec-root-001",
            producer="worker-1",
        )
        self.assertFalse(child_source.is_root)

        with self.assertRaises(ValueError):
            ExecutionSource(source=ExecutionSourceKind.USER, root_execution_id="")

    def test_owner_record_epoch_fencing_and_transitions(self) -> None:
        rec = OwnerRecord(
            execution_id="exec-001",
            owner_id="owner-primary",
            epoch=1,
            state=OwnershipState.OWNED,
        )
        self.assertEqual(rec.state, OwnershipState.OWNED)

        # Cannot transfer directly from OWNED
        with self.assertRaises(InvalidOwnershipTransitionError):
            rec.transfer("owner-secondary", expected_epoch=1)

        # Quiesce then mark handoff ready
        rec.quiesce()
        self.assertEqual(rec.state, OwnershipState.QUIESCING)
        rec.handoff_ready()
        self.assertEqual(rec.state, OwnershipState.HANDOFF_READY)

        # Stale epoch must fail closed
        with self.assertRaises(StaleOwnerEpochError):
            rec.transfer("owner-secondary", expected_epoch=0)

        # Valid transfer increments epoch and restores OWNED state
        rec.transfer("owner-secondary", expected_epoch=1)
        self.assertEqual(rec.owner_id, "owner-secondary")
        self.assertEqual(rec.epoch, 2)
        self.assertEqual(rec.state, OwnershipState.OWNED)

    def test_nonterminal_suspension_and_resume(self) -> None:
        rec = OwnerRecord(
            execution_id="exec-002",
            owner_id="worker-a",
            epoch=5,
        )
        rec.suspend()
        self.assertEqual(rec.state, OwnershipState.SUSPENDED)

        # Stale resume fails
        with self.assertRaises(StaleOwnerEpochError):
            rec.resume("worker-b", expected_epoch=4)

        # Valid resume succeeds
        rec.resume("worker-b", expected_epoch=5)
        self.assertEqual(rec.state, OwnershipState.OWNED)
        self.assertEqual(rec.epoch, 6)
        self.assertEqual(rec.owner_id, "worker-b")

    def test_parent_authoritative_recovery(self) -> None:
        rec = OwnerRecord(
            execution_id="child-001",
            owner_id="crashed-worker",
            epoch=3,
            parent_execution_id="parent-001",
        )
        rec.recover(parent_owner_id="parent-001", current_epoch=3)
        self.assertEqual(rec.owner_id, "parent-001")
        self.assertEqual(rec.epoch, 4)
        self.assertEqual(rec.state, OwnershipState.OWNED)

    def test_runtime_owner_contract(self) -> None:
        owner = RuntimeOwner(
            execution_id="exec-rt-001",
            owner_execution_id="parent-001",
            owner_epoch=0,
            ownership_state=OwnershipState.OWNED,
        )
        self.assertEqual(owner.execution_id, "exec-rt-001")
        self.assertEqual(owner.root_execution_id, "exec-rt-001")
        with self.assertRaises(ValueError):
            RuntimeOwner(
                execution_id="",
                owner_execution_id="p",
                owner_epoch=0,
                ownership_state=OwnershipState.OWNED,
            )


class TestBatch02TimelineAndArtifacts(unittest.TestCase):
    """Batch 02: Durable timeline and typed artifacts."""

    def test_timeline_append_sequence_and_epoch_fencing(self) -> None:
        timeline = ExecutionTimeline("exec-tl-001")
        e0 = ExecutionTimelineEvent(
            execution_id="exec-tl-001",
            sequence=0,
            event_id="evt-0",
            event_type="START",
            occurred_at=datetime.now(UTC),
        )
        timeline.append(e0, owner_epoch=1, expected_owner_epoch=1)
        self.assertEqual(timeline.next_sequence, 1)

        # Stale epoch fails
        e1 = ExecutionTimelineEvent(
            execution_id="exec-tl-001",
            sequence=1,
            event_id="evt-1",
            event_type="STEP",
            occurred_at=datetime.now(UTC),
        )
        with self.assertRaises(StaleOwnerEpochError):
            timeline.append(e1, owner_epoch=1, expected_owner_epoch=2)

        # Non-monotonic sequence fails
        e_bad = ExecutionTimelineEvent(
            execution_id="exec-tl-001",
            sequence=5,
            event_id="evt-bad",
            event_type="STEP",
            occurred_at=datetime.now(UTC),
        )
        with self.assertRaises(ValueError):
            timeline.append(e_bad, owner_epoch=2, expected_owner_epoch=2)

        # Valid append
        timeline.append(e1, owner_epoch=2, expected_owner_epoch=2)
        proj = timeline.project()
        self.assertEqual(proj["total_events"], 2)
        self.assertEqual(proj["last_sequence"], 1)

    def test_typed_artifact_store_content_addressing_and_idempotency(self) -> None:
        store = TypedArtifactStore()
        content = b"console.log('hello world');"
        digest = f"sha256:{hashlib.sha256(content).hexdigest()}"

        artifact = TypedArtifact(
            execution_id="exec-art-001",
            artifact_type="CODE_BUNDLE",
            identity_key="src/index.js",
            digest=digest,
        )

        # Mismatch content digest fails
        with self.assertRaises(ValueError):
            store.put(artifact, raw_content=b"different content")

        # Put with valid content succeeds
        saved = store.put(artifact, raw_content=content)
        self.assertEqual(saved.digest, digest)

        # Idempotent re-put succeeds
        saved2 = store.put(artifact, raw_content=content)
        self.assertEqual(saved2.digest, digest)

        # Conflicting digest for same identity key fails
        conflicting = TypedArtifact(
            execution_id="exec-art-001",
            artifact_type="CODE_BUNDLE",
            identity_key="src/index.js",
            digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        )
        with self.assertRaises(ArtifactConflictError):
            store.put(conflicting)


class TestBatch03ContextAndProvenance(unittest.TestCase):
    """Batch 03: Context envelopes and provenance preservation."""

    def test_context_fork_scope_constraint(self) -> None:
        root_env = ContextEnvelope(
            context_id="ctx-root",
            role="system",
            kind="system_prompt",
            producer="platform",
            trust=ContextTrust.SYSTEM,
            scope=ContextScope.ROOT_ONLY,
            retention_policy="durable",
            replay_policy="preserve",
        )
        # ROOT_ONLY cannot fork to child
        with self.assertRaises(AuthorityViolationError):
            root_env.fork_for_child("child-sub-001")

        lineage_env = ContextEnvelope(
            context_id="ctx-lineage",
            role="developer",
            kind="instructions",
            producer="user",
            trust=ContextTrust.OWNER,
            scope=ContextScope.LINEAGE,
            retention_policy="durable",
            replay_policy="preserve",
        )
        forked = lineage_env.fork_for_child("child-sub-001")
        self.assertEqual(forked.parent_execution_id, "ctx-lineage")
        self.assertEqual(forked.trust, ContextTrust.OWNER)

    def test_compact_context_least_trust_dominates(self) -> None:
        e1 = ContextEnvelope(
            context_id="ctx-1",
            role="user",
            kind="user_message",
            producer="user",
            trust=ContextTrust.OWNER,
            scope=ContextScope.SESSION,
            retention_policy="durable",
            replay_policy="preserve",
            content_digest="sha256:111",
        )
        e2 = ContextEnvelope(
            context_id="ctx-2",
            role="tool",
            kind="tool_output",
            producer="web_scraper",
            trust=ContextTrust.UNTRUSTED,
            scope=ContextScope.SESSION,
            retention_policy="ephemeral",
            replay_policy="preserve",
            content_digest="sha256:222",
        )
        compacted = compact_context([e1, e2])
        # UNTRUSTED dominates
        self.assertEqual(compacted.trust, ContextTrust.UNTRUSTED)
        self.assertTrue(compacted.content_digest.startswith("sha256:"))


class TestBatch04PolicyAndNegotiation(unittest.TestCase):
    """Batch 04: EffectivePolicy intersection, hard-deny, and negotiation."""

    def test_effective_policy_hard_deny_monotonic(self) -> None:
        tenant_policy = Policy(
            allows=frozenset({"repo.read", "repo.write", "net.external"}),
            denies=frozenset(),
        )
        env_policy = Policy(
            allows=frozenset({"repo.read", "repo.write", "net.external"}),
            denies=frozenset({"net.external"}),  # Hard deny on network
        )
        effective = intersect_policies(tenant_policy, env_policy)
        self.assertEqual(effective.allows, frozenset({"repo.read", "repo.write"}))
        self.assertIn("net.external", effective.denies)

    def test_monotonic_authority_narrowing(self) -> None:
        self.assertTrue(monotonic_authority({"read", "write"}, {"read"}))
        self.assertTrue(monotonic_authority({"read", "write"}, {"read", "write"}))
        self.assertFalse(monotonic_authority({"read"}, {"read", "write"}))

    def test_negotiate_capability_scopes(self) -> None:
        status, eff = negotiate(
            requested=["repo.read", "repo.write"],
            supported=["repo.read", "repo.write", "tool.exec"],
        )
        self.assertEqual(status, Negotiation.SUPPORTED_EXACTLY)
        self.assertEqual(eff, frozenset({"repo.read", "repo.write"}))

        status2, eff2 = negotiate(
            requested=["repo.read", "net.outbound"],
            supported=["repo.read"],
        )
        self.assertEqual(status2, Negotiation.SUPPORTED_WITH_NARROWER_SCOPE)
        self.assertEqual(eff2, frozenset({"repo.read"}))

        status3, eff3 = negotiate(
            requested=["admin.delete"],
            supported=["repo.read"],
        )
        self.assertEqual(status3, Negotiation.UNSUPPORTED)
        self.assertEqual(len(eff3), 0)

    def test_runtime_status_observer_zero_side_effect(self) -> None:
        obs = RuntimeStatusObserver(RuntimeState.NOT_STARTED)
        self.assertEqual(obs.observe(), RuntimeState.NOT_STARTED)
        self.assertEqual(obs.connect_calls, 0)
        # Explicit connect
        obs.connect()
        self.assertEqual(obs.connect_calls, 1)
        self.assertEqual(obs.observe(), RuntimeState.CONNECTED)

    def test_capability_inventory_and_connection_state(self) -> None:
        inv = CapabilityInventory(
            adapter_id="adapter-mcp-1",
            protocol_version="2026.1",
            capabilities=("fs.read", "fs.write"),
            approval_modes=("INTERACTIVE", "POLICY_ONLY"),
        )
        self.assertEqual(inv.adapter_id, "adapter-mcp-1")
        self.assertEqual(len(inv.capabilities), 2)

        conn = RuntimeConnectionState(
            adapter_id="adapter-mcp-1",
            observed_at=datetime.now(UTC),
            state=RuntimeState.CONNECTED,
            side_effect_free_observation=True,
        )
        self.assertEqual(conn.state, RuntimeState.CONNECTED)


class TestBatch05LifecycleAndHandoff(unittest.TestCase):
    """Batch 05: Two-phase handoff and interrupt barriers."""

    def test_two_phase_handoff_protocol(self) -> None:
        rec = OwnerRecord("exec-handoff", "owner-a", epoch=1)
        timeline = ExecutionTimeline("exec-handoff")
        protocol = HandoffProtocol(rec, timeline)

        # Cannot transfer prematurely
        with self.assertRaises(InvalidOwnershipTransitionError):
            protocol.transfer("owner-b", expected_epoch=1)

        protocol.quiesce()
        self.assertEqual(rec.state, OwnershipState.QUIESCING)

        protocol.checkpoint()
        protocol.close_writers()
        self.assertEqual(rec.state, OwnershipState.HANDOFF_READY)

        protocol.transfer("owner-b", expected_epoch=1)
        self.assertEqual(rec.owner_id, "owner-b")
        self.assertEqual(rec.epoch, 2)
        self.assertEqual(rec.state, OwnershipState.OWNED)

    def test_interrupt_lifecycle_transcript_barrier(self) -> None:
        rec = OwnerRecord("exec-interrupt", "worker-1", epoch=1)
        timeline = ExecutionTimeline("exec-interrupt")
        interrupt_mgr = InterruptLifecycle(timeline, rec)

        interrupt_mgr.interrupt("SIGTERM from host")
        self.assertEqual(rec.state, OwnershipState.SUSPENDED)
        self.assertEqual(timeline.next_sequence, 1)
        event = timeline.list_events()[0]
        self.assertEqual(event.event_type, "LIFECYCLE_INTERRUPT")
        self.assertEqual(event.payload.get("reason"), "SIGTERM from host")


class TestBatch06SessionSafetyAndPeerBinding(unittest.TestCase):
    """Batch 06: Reviewer/verifier isolation and peer bindings."""

    def test_reviewer_cannot_inherit_user_extensions(self) -> None:
        # Enforce Invariant 9: Reviewer/Verifier cannot inherit user extensions/MCP
        with self.assertRaises(AuthorityViolationError):
            SessionInheritancePolicy(
                policy_id="pol-rev-1",
                session_role=SessionRole.REVIEWER,
                inherit_extensions=True,
            )

        with self.assertRaises(AuthorityViolationError):
            SessionInheritancePolicy(
                policy_id="pol-ver-1",
                session_role=SessionRole.VERIFIER,
                inherit_mcp_servers=True,
            )

        # Valid reviewer policy
        rev_pol = SessionInheritancePolicy(
            policy_id="pol-rev-valid",
            session_role=SessionRole.REVIEWER,
            inherit_extensions=False,
            inherit_mcp_servers=False,
        )
        self.assertEqual(rev_pol.session_role, SessionRole.REVIEWER)

    def test_peer_binding_contract(self) -> None:
        pb = PeerBinding(
            tenant_id="tenant-alpha",
            peer_identity="peer-agent-99",
            agent_runtime_id="codex-runtime",
            authority_scope={"allow": ["repo.read"]},
            binding_version="3.2.0",
        )
        self.assertEqual(pb.tenant_id, "tenant-alpha")
        self.assertEqual(pb.peer_identity, "peer-agent-99")


class TestBatch07ToolAndApprovalJournal(unittest.TestCase):
    """Batch 07: Effect-level approvals, tool journals, and side-effects."""

    def test_approval_matching_and_expiration(self) -> None:
        binding = {
            "execution_plan_digest": "plan-hash-123",
            "action_kind": ApprovalActionKind.EXEC_COMMAND,
            "resource_digest": "res-hash-456",
            "decision": ApprovalDecision.ALLOW,
            "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        }

        current = {
            "execution_plan_digest": "plan-hash-123",
            "action_kind": ApprovalActionKind.EXEC_COMMAND,
            "resource_digest": "res-hash-456",
        }
        self.assertTrue(approval_matches(binding, current))

        # Different action kind must fail
        mismatched_action = dict(current, action_kind=ApprovalActionKind.WRITE_STDIN)
        self.assertFalse(approval_matches(binding, mismatched_action))

        # Expired binding must fail
        expired_binding = dict(
            binding,
            expires_at=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        )
        self.assertFalse(approval_matches(expired_binding, current))

    def test_tool_call_journal_failed_replay(self) -> None:
        journal_entry = ToolCallJournal(
            call_id="call-fail-001",
            capability="fs.delete",
            adapter="local-fs",
            started_at=datetime.now(UTC),
            terminal_status=ToolTerminalStatus.FAILED,
            error="PermissionDenied: path is read-only",
        )
        self.assertEqual(journal_entry.terminal_status, ToolTerminalStatus.FAILED)
        self.assertIn("PermissionDenied", str(journal_entry.error))

    def test_side_effect_receipt_contract(self) -> None:
        receipt = SideEffectReceipt(
            receipt_id="rec-001",
            effect_kind="DB_WRITE",
            idempotency_key="tx-12345",
            status=SideEffectStatus.CONFIRMED,
            occurred_at=datetime.now(UTC),
            resource_digest="sha256:db-table",
        )
        self.assertEqual(receipt.status, SideEffectStatus.CONFIRMED)
        self.assertEqual(receipt.idempotency_key, "tx-12345")


class TestBatch08ResultFenceAndCheckpoint(unittest.TestCase):
    """Batch 08: Result fences and file/directory transformation path kinds."""

    def test_repository_checkpoint_preserves_path_kinds(self) -> None:
        entry = RepositoryCheckpointEntry(
            path="config",
            old_kind=PathKind.FILE,
            new_kind=PathKind.DIRECTORY,
            old_digest="sha256:aaa",
            new_digest="sha256:bbb",
        )
        self.assertEqual(entry.old_kind, PathKind.FILE)
        self.assertEqual(entry.new_kind, PathKind.DIRECTORY)

        cp = RepositoryCheckpoint(
            checkpoint_id="cp-001",
            repository="elmos",
            base_revision="v3.1.0",
            entries=(entry,),
            digest="sha256:cp-digest",
        )
        self.assertEqual(len(cp.entries), 1)

    def test_result_fence_lifecycle_and_builder_publication_denial(self) -> None:
        fence = ResultFence(
            fence_id="fence-001",
            execution_id="exec-001",
            candidate_checkpoint_id="cp-001",
        )
        self.assertEqual(fence.state, ResultFenceState.CANDIDATE)

        # Unverified fence cannot be certified or published
        with self.assertRaises(InvalidOwnershipTransitionError):
            fence.mark_certified()

        fence.intercept()
        fence.start_reconciliation()
        fence.mark_verified("manifest-001")
        self.assertEqual(fence.state, ResultFenceState.VERIFIED)

        # Cannot publish while only VERIFIED
        with self.assertRaises(PublicationDeniedError):
            fence.publish("pub-req-1")

        fence.mark_certified()
        self.assertEqual(fence.state, ResultFenceState.CERTIFIED)

        # Now can publish
        fence.publish("pub-req-1")
        self.assertEqual(fence.state, ResultFenceState.PUBLISHED)


class TestBatch09WorkerPoolAndFingerprint(unittest.TestCase):
    """Batch 09: Worker fabric hardening and environment fingerprinting."""

    def test_environment_fingerprint_matching(self) -> None:
        fp1 = EnvironmentFingerprint(
            platform="darwin",
            arch="arm64",
            libc="bsd",
            toolchain_hashes={"python": "3.12.9"},
        )
        fp2 = EnvironmentFingerprint(
            platform="linux",
            arch="x86_64",
            libc="glibc-2.35",
            toolchain_hashes={"python": "3.12.9"},
        )
        pool = PreparedWorkerPool()
        pool.register("worker-mac", fp1)
        pool.register("worker-linux", fp2)

        matched = pool.find_matching(fp1)
        self.assertEqual(matched, ["worker-mac"])


class TestBatch10ReleaseAssuranceAndPublicationBroker(unittest.TestCase):
    """Batch 10: Non-self-certification release gates and publication authority."""

    def test_release_gate_pending_or_waived_blocks(self) -> None:
        # All PASS + exact verified succeeds
        self.assertTrue(release_gate([VerificationStatus.PASS, VerificationStatus.PASS], exact_artifact_verified=True))

        # PENDING blocks release (Invariant 16)
        self.assertFalse(release_gate([VerificationStatus.PASS, VerificationStatus.PENDING], exact_artifact_verified=True))

        # WAIVED blocks unassisted release
        self.assertFalse(release_gate([VerificationStatus.PASS, VerificationStatus.WAIVED], exact_artifact_verified=True))

        # Unverified artifact bytes blocks release (Invariant 20)
        self.assertFalse(release_gate([VerificationStatus.PASS], exact_artifact_verified=False))

    def test_publication_broker_authority_separation(self) -> None:
        broker = PublicationBroker(authorized_publisher_id="trusted-publisher-01")
        fence = ResultFence(
            fence_id="f-1",
            execution_id="e-1",
            candidate_checkpoint_id="c-1",
            state=ResultFenceState.CERTIFIED,
        )
        req = PublicationRequest(
            request_id="req-1",
            certified_checkpoint_id="c-1",
            action=PublicationAction.RELEASE,
            status=PublicationRequestStatus.PENDING,
        )
        valid_approval = ApprovalBinding(
            approval_id="app-1",
            execution_plan_digest="plan-1",
            action_kind=ApprovalActionKind.PUBLICATION,
            decision=ApprovalDecision.ALLOW,
        )

        # Unauthorized caller fails
        with self.assertRaises(PublicationDeniedError):
            broker.execute_publication("unauthorized-worker", fence, req, valid_approval)

        # Authorized broker succeeds
        broker.execute_publication("trusted-publisher-01", fence, req, valid_approval)
        self.assertEqual(fence.state, ResultFenceState.PUBLISHED)

    def test_release_evidence_manifest_contract(self) -> None:
        check = ReleaseVerificationCheck(
            check_id="chk-unit-01",
            status=VerificationStatus.PASS,
            evidence_id="ev-999",
        )
        self.assertEqual(check.status, VerificationStatus.PASS)

        manifest = ReleaseEvidenceManifest(
            release_id="rel-3.2.0",
            repository_commit="commit-abcdef",
            verification=(check,),
            publication={"target": "registry"},
            status=VerificationStatus.PASS,
        )
        self.assertEqual(manifest.release_id, "rel-3.2.0")
        self.assertEqual(len(manifest.verification), 1)


class TestBatch11And12EngineeringObserver(unittest.TestCase):
    """Batch 11 & 12: Observer diagnostics for stuck loops and drift."""

    def test_detect_stuck_loop(self) -> None:
        calls = [
            ToolCallJournal(
                call_id=f"c-{i}",
                capability="network.fetch",
                adapter="http",
                started_at=datetime.now(UTC),
                terminal_status=ToolTerminalStatus.FAILED,
            )
            for i in range(3)
        ]
        self.assertTrue(EngineeringObserver.detect_stuck_loop(calls, max_repeated_failures=3))

        calls_healthy = [
            ToolCallJournal(
                call_id="c-0",
                capability="network.fetch",
                adapter="http",
                started_at=datetime.now(UTC),
                terminal_status=ToolTerminalStatus.SUCCEEDED,
            )
        ]
        self.assertFalse(EngineeringObserver.detect_stuck_loop(calls_healthy))

    def test_detect_runtime_drift(self) -> None:
        expected = EnvironmentFingerprint(platform="darwin", arch="arm64", libc="bsd")
        actual = EnvironmentFingerprint(platform="linux", arch="x86_64", libc="gnu")
        self.assertTrue(EngineeringObserver.detect_runtime_drift(expected, actual))


if __name__ == "__main__":
    unittest.main()
