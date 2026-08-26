"""Repository-context projection and fail-closed compaction orchestration."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import PROJECT, TENANT, digest
from elmos_build_cache.canonical import canonical_json_text
from elmos_build_cache.clock import ManualClock
from elmos_build_cache.context_compaction import (
    CompactionNeed,
    CompactionPolicy,
    ContextCheckpoint,
    ContextCheckpointStatus,
)
from elmos_build_cache.context_ledger import ContextEventType, ContextLedgerEvent, RepositoryContextLedger
from elmos_build_cache.context_runtime import (
    ChangeContextObservation,
    ChangeObservationKind,
    CheckpointContextObservation,
    CompactionTransitionStatus,
    ContextCompactionRuntime,
    ContextPromptProjection,
    FileContextObservation,
    FileObservationKind,
    PromptContextState,
    RepositoryContextRuntime,
    ResolvedContextContent,
    ShadowEquivalenceDecision,
    SnapshotBoundContextObservation,
    SummaryContextObservation,
    SymbolContextObservation,
    ToolContextObservation,
    ValidationContextObservation,
)
from elmos_build_cache.db.store import SqliteMetadataStore
from elmos_build_cache.errors import ContractViolation, CorruptObject, IdempotencyConflict
from elmos_build_cache.prompt_cache import PromptIdentity, PromptProvider
from elmos_build_cache.prompt_runtime import (
    CanonicalPromptAssembler,
    CanonicalPromptInputs,
    CurrentPromptTurn,
    StablePromptSections,
)


def make_ledger(
    store: SqliteMetadataStore,
    *,
    create_if_missing: bool = True,
) -> RepositoryContextLedger:
    return RepositoryContextLedger(
        store,
        TENANT,
        PROJECT,
        "runtime-stream-1",
        "refs/heads/main@abc123",
        digest("1"),
        create_if_missing=create_if_missing,
    )


class DeterministicContentResolver:
    def __init__(self, marker: str = "RAW-RESOLVED-CONTENT-CANARY") -> None:
        self.marker = marker
        self.calls: list[str] = []

    def resolve(self, event: ContextLedgerEvent) -> ResolvedContextContent:
        self.calls.append(event.event_id)
        return ResolvedContextContent.for_event(
            event,
            canonical_json_text(
                {
                    "marker": self.marker,
                    "event_type": event.event_type.value,
                    "event_id": event.event_id,
                    "event_digest": event.event_digest,
                }
            ),
        )


def prompt_identity() -> PromptIdentity:
    return PromptIdentity(
        tenant_scope_digest=digest("2"),
        provider=PromptProvider.OPENAI,
        provider_namespace_digest=digest("3"),
        model="model-v1",
        effort_profile="high",
        tool_schema_digest=digest("4"),
        compatibility_digest=digest("5"),
    )


def assemble_projection(projection: ContextPromptProjection) -> str:
    assembly = CanonicalPromptAssembler().assemble(
        CanonicalPromptInputs(
            identity=prompt_identity(),
            stable=StablePromptSections(
                system="system",
                safety="safety",
                tools="tools",
                schema="schema",
                skills="skills",
                repository="repository",
            ),
            context=projection.fragments,
            current_turn=CurrentPromptTurn("turn-1", "current turn"),
        )
    )
    return assembly.assembly_digest


def test_typed_observations_append_exact_ledger_events_without_raw_metadata(
    store: SqliteMetadataStore,
) -> None:
    raw_key = "RAW-PROMPT-IDEMPOTENCY-CANARY API_KEY=must-never-persist"
    resolver = DeterministicContentResolver()
    runtime = RepositoryContextRuntime(make_ledger(store), resolver)
    first = runtime.record(
        FileContextObservation(
            FileObservationKind.READ,
            "src/main.py",
            digest("a"),
            raw_key,
        ),
        expected_sequence=0,
    )
    runtime.record(
        ToolContextObservation(
            tool="pytest",
            idempotency_key="tool-1",
            result_digest=digest("b"),
            status="PASS",
            duration_ms=17,
        ),
        expected_sequence=1,
        expected_head_digest=first.event_digest,
    )
    runtime.record(
        ValidationContextObservation(
            validation_level="focused",
            idempotency_key="validation-1",
            result_digest=digest("c"),
            status="PASS",
            suite_id="context-runtime",
        )
    )
    runtime.record(
        ChangeContextObservation(
            ChangeObservationKind.CHANGED,
            "src/main.py",
            "change-1",
            content_digest=digest("d"),
            supersedes_event_id=first.event_id,
        )
    )

    assert [event.event_type for event in runtime.ledger.events()] == [
        ContextEventType.FILE_READ,
        ContextEventType.TOOL_OBSERVED,
        ContextEventType.VALIDATION_OBSERVED,
        ContextEventType.CONTENT_CHANGED,
    ]
    projection = runtime.project()
    assert [fragment.sequence for fragment in projection.fragments] == [1, 2, 3, 4]
    assert resolver.calls == [event.event_id for event in runtime.ledger.events()]

    durable_rows = store.query(
        "SELECT idempotency_key, payload FROM context_ledger_events ORDER BY sequence"
    )
    durable_text = json.dumps([tuple(row) for row in durable_rows], sort_keys=True)
    manifest_text = json.dumps(projection.manifest(), sort_keys=True)
    for forbidden in (
        raw_key,
        "RAW-PROMPT-IDEMPOTENCY-CANARY",
        "must-never-persist",
        resolver.marker,
        "RAW-RESOLVED-CONTENT-CANARY",
    ):
        assert forbidden not in durable_text
        assert forbidden not in manifest_text
    assert all(str(row[0]).startswith("ctxrt-") for row in durable_rows)


def test_snapshot_symbol_summary_and_checkpoint_events_project_without_content_leaks(
    store: SqliteMetadataStore,
) -> None:
    runtime = RepositoryContextRuntime(make_ledger(store))
    snapshot = runtime.record(
        SnapshotBoundContextObservation(digest("1"), "snapshot-1")
    )
    file_read = runtime.record(
        FileContextObservation(
            FileObservationKind.READ,
            "src/main.py",
            digest("a"),
            "file-1",
        )
    )
    symbol = runtime.record(
        SymbolContextObservation(
            symbol_ref="module.main",
            logical_path="src/main.py",
            symbol_digest=digest("b"),
            content_digest=digest("a"),
            idempotency_key="symbol-1",
            source_event_id=file_read.event_id,
        )
    )
    summary = runtime.record(
        SummaryContextObservation(
            summary_digest=digest("c"),
            source_event_ids=(file_read.event_id, symbol.event_id),
            idempotency_key="summary-1",
            token_count=12,
        )
    )
    runtime.record(
        CheckpointContextObservation(
            checkpoint_id="checkpoint-1",
            checkpoint_digest=digest("d"),
            source_event_ids=(summary.event_id,),
            ledger_sequence=4,
            idempotency_key="checkpoint-1",
        )
    )

    assert [event.event_type for event in runtime.ledger.events()] == [
        ContextEventType.SNAPSHOT_BOUND,
        ContextEventType.FILE_READ,
        ContextEventType.SYMBOL_READ,
        ContextEventType.SUMMARY_WRITTEN,
        ContextEventType.CONTEXT_CHECKPOINT,
    ]
    projection = runtime.project()
    assert [fragment.sequence for fragment in projection.fragments] == [1, 2, 3, 4, 5]
    assert projection.ledger_head_digest == runtime.ledger.position().head_event_digest
    assert snapshot.event_digest != file_read.event_digest


def test_typed_snapshot_and_provenance_bindings_fail_closed(
    store: SqliteMetadataStore,
) -> None:
    runtime = RepositoryContextRuntime(make_ledger(store))
    with pytest.raises(ContractViolation, match="snapshot binding"):
        runtime.record(SnapshotBoundContextObservation(digest("f"), "snapshot-foreign"))
    with pytest.raises(ContractViolation, match="unknown source event"):
        runtime.record(
            SymbolContextObservation(
                symbol_ref="module.main",
                logical_path="src/main.py",
                symbol_digest=digest("b"),
                content_digest=digest("a"),
                idempotency_key="symbol-foreign",
                source_event_id="ctxevt-foreign",
            )
        )


def test_record_replay_is_exact_and_conflicting_reuse_fails_closed(
    store: SqliteMetadataStore,
) -> None:
    runtime = RepositoryContextRuntime(make_ledger(store))
    observation = FileContextObservation(
        FileObservationKind.READ,
        "src/main.py",
        digest("a"),
        "same-external-key",
    )
    first = runtime.record(observation)
    replay = runtime.record(observation, expected_sequence=0)

    assert replay == first
    assert runtime.ledger.position().sequence == 1
    with pytest.raises(IdempotencyConflict):
        runtime.record(replace(observation, content_digest=digest("b")))
    assert runtime.ledger.position().sequence == 1


def test_projection_replay_is_append_only_and_preserves_prompt_prefix(
    store: SqliteMetadataStore,
) -> None:
    runtime = RepositoryContextRuntime(make_ledger(store), DeterministicContentResolver())
    runtime.record(
        FileContextObservation(
            FileObservationKind.READ,
            "src/a.py",
            digest("a"),
            "read-a",
        )
    )
    previous = runtime.project()
    previous_prompt = CanonicalPromptAssembler().assemble(
        CanonicalPromptInputs(
            identity=prompt_identity(),
            stable=StablePromptSections("system", "safety", "tools", "schema", "skills", "repository"),
            context=previous.fragments,
            current_turn=CurrentPromptTurn("turn-1", "first turn"),
        )
    )

    runtime.record(
        ToolContextObservation(
            tool="ruff",
            idempotency_key="tool-ruff",
            result_digest=digest("b"),
            status="PASS",
        )
    )
    current = runtime.project()
    current_prompt = CanonicalPromptAssembler().assemble(
        CanonicalPromptInputs(
            identity=prompt_identity(),
            stable=StablePromptSections("system", "safety", "tools", "schema", "skills", "repository"),
            context=current.fragments,
            current_turn=CurrentPromptTurn("turn-2", "second turn"),
        )
    )

    ContextPromptProjection.assert_append_only_successor(previous, current)
    CanonicalPromptAssembler().compiler.assert_append_only_successor(
        previous_prompt.compiled,
        current_prompt.compiled,
    )
    assert current.fragments[: len(previous.fragments)] == previous.fragments
    assert previous_prompt.compiled.stable_prefix_digest == current_prompt.compiled.stable_prefix_digest


def test_restart_replays_identical_projection_and_prompt_digest(
    tmp_path: Path,
    clock: ManualClock,
) -> None:
    path = tmp_path / "context-runtime.sqlite"
    first_store = SqliteMetadataStore.open(path, clock)
    try:
        first_runtime = RepositoryContextRuntime(make_ledger(first_store), DeterministicContentResolver())
        first_runtime.record(
            FileContextObservation(
                FileObservationKind.READ,
                "src/main.py",
                digest("a"),
                "read-main",
            )
        )
        first_runtime.record(
            ValidationContextObservation(
                validation_level="focused",
                idempotency_key="validation-focused",
                result_digest=digest("b"),
                status="PASS",
            )
        )
        before = first_runtime.project()
        before_prompt_digest = assemble_projection(before)
        before_manifest = canonical_json_text(before.manifest())
    finally:
        first_store.close()

    restarted_store = SqliteMetadataStore.open(path, clock)
    try:
        restarted_runtime = RepositoryContextRuntime(
            make_ledger(restarted_store, create_if_missing=False),
            DeterministicContentResolver(),
        )
        after = restarted_runtime.project()
        assert canonical_json_text(after.manifest()) == before_manifest
        assert after.context_digest == before.context_digest
        assert assemble_projection(after) == before_prompt_digest
    finally:
        restarted_store.close()


@pytest.mark.parametrize(
    ("field", "foreign"),
    [
        ("tenant_id", "tenant-foreign"),
        ("project_id", "project-foreign"),
        ("stream_id", "stream-foreign"),
        ("repository_snapshot_digest", digest("9")),
        ("event_id", "event-foreign"),
        ("event_digest", digest("8")),
    ],
)
def test_resolver_cross_scope_or_resource_binding_fails_closed(
    store: SqliteMetadataStore,
    field: str,
    foreign: str,
) -> None:
    runtime = RepositoryContextRuntime(make_ledger(store))
    runtime.record(
        FileContextObservation(
            FileObservationKind.READ,
            "src/main.py",
            digest("a"),
            "read-main",
        )
    )

    class ForeignResolver:
        def resolve(self, event: ContextLedgerEvent) -> ResolvedContextContent:
            valid = ResolvedContextContent.for_event(event, "transient context")
            return replace(valid, **{field: foreign})

    runtime.resolver = ForeignResolver()
    with pytest.raises(ContractViolation, match="scope or resource boundary"):
        runtime.project()
    assert runtime.ledger.position().sequence == 1


def test_default_projection_is_local_metadata_only_and_content_free(
    store: SqliteMetadataStore,
) -> None:
    runtime = RepositoryContextRuntime(make_ledger(store))
    runtime.record(
        ToolContextObservation(
            tool="local-tool",
            idempotency_key="local-tool-1",
            result_digest=digest("a"),
            status="PASS",
        )
    )

    projection = runtime.project()
    assert len(projection.fragments) == 1
    assert projection.fragments[0].content.startswith("{")
    assert "content" not in projection.manifest()["fragments"][0]


def checkpoint(checkpoint_id: str, previous_checkpoint_id: str | None) -> ContextCheckpoint:
    return ContextCheckpoint(
        tenant_id=TENANT,
        project_id=PROJECT,
        stream_id="runtime-stream-1",
        checkpoint_id=checkpoint_id,
        ledger_sequence=2,
        ledger_head_digest=digest("a"),
        repository_snapshot_digest=digest("1"),
        compatibility_group="model-family-v1",
        source_sequence_start=1,
        source_sequence_end=2,
        sections={},
        external_artifact_refs=(),
        checkpoint_digest=digest("b"),
        previous_checkpoint_id=previous_checkpoint_id,
        status=ContextCheckpointStatus.ACTIVE,
        warm_evidence_digest=digest("c"),
        created_at=0.0,
        warmed_at=0.0,
        adopted_at=0.0,
        rolled_back_at=None,
    )


class FakeCompactionService:
    def __init__(self, *, active_checkpoint_id: str | None = "checkpoint-old") -> None:
        self.policy = CompactionPolicy(
            soft_limit_tokens=100,
            hard_limit_tokens=120,
            reserved_future_tokens=10,
        )
        self.active_checkpoint_id = active_checkpoint_id
        self.adopt_calls: list[tuple[str, str | None]] = []
        self.rollback_calls: list[str] = []
        self.fail_adopt = False
        self.fail_rollback = False
        self.return_wrong_checkpoint = False

    def adopt(
        self,
        checkpoint_id: str,
        *,
        expected_active_checkpoint_id: str | None = None,
    ) -> ContextCheckpoint:
        self.adopt_calls.append((checkpoint_id, expected_active_checkpoint_id))
        if self.fail_adopt:
            raise RuntimeError("injected atomic adoption failure")
        previous = self.active_checkpoint_id
        self.active_checkpoint_id = checkpoint_id
        returned = "checkpoint-wrong" if self.return_wrong_checkpoint else checkpoint_id
        return checkpoint(returned, previous)

    def rollback(self, checkpoint_id: str) -> ContextCheckpoint:
        self.rollback_calls.append(checkpoint_id)
        if self.fail_rollback:
            raise RuntimeError("injected rollback uncertainty")
        self.active_checkpoint_id = "checkpoint-old"
        return checkpoint("checkpoint-old", None)


class RecordingComparator:
    def __init__(
        self,
        decision: ShadowEquivalenceDecision | object,
        *,
        fail: bool = False,
    ) -> None:
        self.decision = decision
        self.fail = fail
        self.calls: list[tuple[PromptContextState, PromptContextState]] = []

    def compare(
        self,
        baseline: PromptContextState,
        candidate: PromptContextState,
    ) -> ShadowEquivalenceDecision:
        self.calls.append((baseline, candidate))
        if self.fail:
            raise RuntimeError("injected comparator failure")
        return self.decision  # type: ignore[return-value]


class RecordingVerifier:
    def __init__(self, result: bool, *, fail: bool = False) -> None:
        self.result = result
        self.fail = fail
        self.calls: list[PromptContextState] = []

    def verify(self, candidate: PromptContextState) -> bool:
        self.calls.append(candidate)
        if self.fail:
            raise RuntimeError("injected verification failure")
        return self.result


def context_states() -> tuple[PromptContextState, PromptContextState]:
    return (
        PromptContextState(digest("d"), digest("e"), "checkpoint-old"),
        PromptContextState(digest("f"), digest("6"), "checkpoint-new"),
    )


def equivalent_decision() -> ShadowEquivalenceDecision:
    return ShadowEquivalenceDecision(True, "EQUIVALENT", digest("7"))


def test_compaction_below_threshold_never_compares_or_adopts() -> None:
    baseline, candidate = context_states()
    service = FakeCompactionService()
    comparator = RecordingComparator(equivalent_decision())

    result = ContextCompactionRuntime(service, comparator).transition(
        current_tokens=79,
        predicted_next_turn_tokens=10,
        baseline=baseline,
        candidate=candidate,
    )

    assert result.need is CompactionNeed.NONE
    assert result.status is CompactionTransitionStatus.NOT_NEEDED
    assert result.active_prompt_digest == baseline.prompt_digest
    assert comparator.calls == []
    assert service.adopt_calls == []


@pytest.mark.parametrize("mode", ["rejected", "failed", "invalid", "adopt-failed"])
def test_compaction_rejection_and_failures_retain_original_prompt_digest(mode: str) -> None:
    baseline, candidate = context_states()
    service = FakeCompactionService()
    decision: ShadowEquivalenceDecision | object = ShadowEquivalenceDecision(
        False,
        "NOT_EQUIVALENT",
        digest("7"),
    )
    comparator = RecordingComparator(decision)
    if mode == "failed":
        comparator.fail = True
    elif mode == "invalid":
        comparator.decision = {"equivalent": True}
    elif mode == "adopt-failed":
        comparator.decision = equivalent_decision()
        service.fail_adopt = True

    result = ContextCompactionRuntime(service, comparator).transition(
        current_tokens=90,
        predicted_next_turn_tokens=0,
        baseline=baseline,
        candidate=candidate,
    )

    expected_status = {
        "rejected": CompactionTransitionStatus.EQUIVALENCE_REJECTED,
        "failed": CompactionTransitionStatus.COMPARATOR_FAILED,
        "invalid": CompactionTransitionStatus.COMPARATOR_FAILED,
        "adopt-failed": CompactionTransitionStatus.ADOPTION_FAILED,
    }[mode]
    assert result.need is CompactionNeed.PLAN
    assert result.status is expected_status
    assert result.active_prompt_digest == baseline.prompt_digest
    assert service.active_checkpoint_id == baseline.checkpoint_id


def test_equivalent_compaction_adopts_candidate_only_after_shadow_comparison() -> None:
    baseline, candidate = context_states()
    service = FakeCompactionService()
    comparator = RecordingComparator(equivalent_decision())

    result = ContextCompactionRuntime(service, comparator).transition(
        current_tokens=100,
        predicted_next_turn_tokens=10,
        baseline=baseline,
        candidate=candidate,
    )

    assert result.need is CompactionNeed.REQUIRED
    assert result.status is CompactionTransitionStatus.ADOPTED
    assert result.active_prompt_digest == candidate.prompt_digest
    assert result.comparison_evidence_digest == digest("7")
    assert comparator.calls == [(baseline, candidate)]
    assert service.adopt_calls == [("checkpoint-new", "checkpoint-old")]
    assert service.active_checkpoint_id == "checkpoint-new"


@pytest.mark.parametrize("verifier_fails", [False, True])
def test_post_adoption_rejection_rolls_back_and_restores_original_digest(
    verifier_fails: bool,
) -> None:
    baseline, candidate = context_states()
    service = FakeCompactionService()
    verifier = RecordingVerifier(False, fail=verifier_fails)

    result = ContextCompactionRuntime(
        service,
        RecordingComparator(equivalent_decision()),
        adopted_verifier=verifier,
    ).transition(
        current_tokens=90,
        predicted_next_turn_tokens=0,
        baseline=baseline,
        candidate=candidate,
    )

    assert result.status is CompactionTransitionStatus.ROLLED_BACK
    assert result.active_prompt_digest == baseline.prompt_digest
    assert result.active_checkpoint_id == baseline.checkpoint_id
    assert service.rollback_calls == ["checkpoint-new"]
    assert service.active_checkpoint_id == "checkpoint-old"


def test_unknown_rollback_never_falsely_claims_original_prompt_digest() -> None:
    baseline, candidate = context_states()
    service = FakeCompactionService()
    service.fail_rollback = True
    runtime = ContextCompactionRuntime(
        service,
        RecordingComparator(equivalent_decision()),
        adopted_verifier=RecordingVerifier(False),
    )

    with pytest.raises(CorruptObject, match="rollback is unknown"):
        runtime.transition(
            current_tokens=90,
            predicted_next_turn_tokens=0,
            baseline=baseline,
            candidate=candidate,
        )
    assert service.active_checkpoint_id == "checkpoint-new"


def test_compaction_transition_manifest_contains_only_digests_and_closed_metadata() -> None:
    baseline, candidate = context_states()
    result = ContextCompactionRuntime(
        FakeCompactionService(),
        RecordingComparator(equivalent_decision()),
    ).transition(
        current_tokens=90,
        predicted_next_turn_tokens=0,
        baseline=baseline,
        candidate=candidate,
    )

    assert set(result.manifest()) == {
        "schema_version",
        "kind",
        "need",
        "status",
        "baseline_prompt_digest",
        "candidate_prompt_digest",
        "active_prompt_digest",
        "active_checkpoint_id",
        "reason_code",
        "comparison_evidence_digest",
    }
    assert not any(isinstance(value, dict | list) for value in result.manifest().values())
