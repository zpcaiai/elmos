"""Prefix-stable context planner: acceptance gates, invariants and mandatory negatives.

Test names follow the gate / negative-test ids in
``skills/prefix-stable-context-planner/acceptance.yaml``.  The headline test is
:func:`test_appending_a_volatile_block_leaves_the_shared_prefix_byte_identical`:
it plans twice, appends a volatile block the second time, and compares the shared
prefix's block order *and* its digests.  Nothing here sleeps, touches the network
or reads the wall clock.
"""

from __future__ import annotations

from typing import Any

import pytest

from elmos_autonomy_kernel.contextplan import (
    DEFAULT_MAX_BREAKPOINTS,
    UNTRUSTED_KINDS,
    BlockKind,
    BlockRole,
    BudgetDecision,
    ContextBlock,
    EvictionReason,
    StabilityClass,
    handle,
    plan,
)
from elmos_autonomy_kernel.contracts import Status
from elmos_autonomy_kernel.errors import KernelError
from elmos_autonomy_kernel.registry import dispatch

SKILL_ID = "prefix-stable-context-planner"
SNAPSHOT_SHA = "sha256:" + "a" * 64
OTHER_SHA = "sha256:" + "b" * 64


# --- fixtures ----------------------------------------------------------------


def block(block_id: str, *, role: BlockRole = BlockRole.USER,
          kind: BlockKind = BlockKind.FILE,
          stability: StabilityClass = StabilityClass.SLOW,
          cost: int | None = 10, required: bool = False,
          snapshot_sha: str = SNAPSHOT_SHA) -> ContextBlock:
    return ContextBlock(
        block_id=block_id, role=role, kind=kind, stability_class=stability,
        digest="sha256:" + block_id.encode("utf-8").hex().ljust(64, "0")[:64],
        token_cost=cost, required=required, snapshot_sha=snapshot_sha,
    )


def standard_blocks() -> tuple[ContextBlock, ...]:
    """Two immutable, two slow, two volatile — one of each trust posture."""

    return (
        block("sys-prompt", role=BlockRole.SYSTEM, kind=BlockKind.SYSTEM,
              stability=StabilityClass.IMMUTABLE, cost=100, required=True),
        block("spec-1", role=BlockRole.SYSTEM, kind=BlockKind.SPEC,
              stability=StabilityClass.IMMUTABLE, cost=50, required=True),
        block("tools-1", role=BlockRole.TOOL, kind=BlockKind.TOOL_SCHEMA,
              stability=StabilityClass.SLOW, cost=40),
        block("repo-map-1", kind=BlockKind.REPO_MAP, stability=StabilityClass.SLOW, cost=30),
        block("history-1", kind=BlockKind.HISTORY, stability=StabilityClass.VOLATILE, cost=20),
        block("task-current", kind=BlockKind.TASK, stability=StabilityClass.VOLATILE,
              cost=10, required=True),
    )


class FixedCounter:
    """A token counter that answers a declared number per block id."""

    def __init__(self, counts: dict[str, int]) -> None:
        self.counts = counts
        self.calls: list[str] = []

    def count(self, item: ContextBlock) -> int:
        self.calls.append(item.block_id)
        return self.counts[item.block_id]


class BrokenCounter:
    """A counter that cannot answer.  It must raise, never return a placeholder."""

    def count(self, item: ContextBlock) -> int:
        raise KernelError(
            code="RETRIEVAL_MISS",
            message=f"no tokeniser is available for {item.block_id!r}",
            recommended_action="configure a tokeniser for this provider",
        )


def base_request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "skill_metadata": {"skillId": "planner", "digest": "sha256:" + "1" * 64,
                           "tokenCost": 100},
        "task_spec": {"taskSpecId": "spec-1", "digest": "sha256:" + "2" * 64,
                      "tokenCost": 50, "snapshotSha": SNAPSHOT_SHA},
        "repository_index": {"indexId": "index-1", "digest": "sha256:" + "3" * 64,
                             "tokenCost": 30, "snapshotSha": SNAPSHOT_SHA},
        "current_step": {"stepId": "step-1", "digest": "sha256:" + "4" * 64,
                         "tokenCost": 10},
    }
    for key, value in overrides.items():
        if value is None and key in request:
            del request[key]
        elif isinstance(value, dict) and isinstance(request.get(key), dict):
            request[key] = {**request[key], **value}
        else:
            request[key] = value
    return request


# --- the headline property ---------------------------------------------------


def test_appending_a_volatile_block_leaves_the_shared_prefix_byte_identical() -> None:
    """The whole module exists for this: a later addition cannot move the prefix.

    The second plan appends a volatile block that sorts after everything already
    present, so the first plan must be a *prefix* of the second — same block
    order and the same per-position prefix digests, byte for byte.  A provider
    cache keys on exactly those bytes.
    """

    first = plan(standard_blocks())
    later = plan((*standard_blocks(),
                  block("task-zz-appended", kind=BlockKind.TASK,
                        stability=StabilityClass.VOLATILE, cost=15)))

    shared = len(first.blocks)
    assert later.block_ids[:shared] == first.block_ids
    assert later.prefix_digests[:shared] == first.prefix_digests
    assert later.blocks[:shared] == first.blocks
    assert len(later.blocks) == shared + 1
    assert later.prefix_digest != first.prefix_digest


def test_appending_a_volatile_block_does_not_move_the_stable_prefix() -> None:
    """Even a volatile block that sorts *among* the volatile tail leaves the head alone."""

    first = plan(standard_blocks())
    later = plan((*standard_blocks(),
                  block("history-0-inserted", kind=BlockKind.HISTORY,
                        stability=StabilityClass.VOLATILE, cost=5)))

    stable = first.stable_prefix_length
    assert stable == 4
    assert later.stable_prefix_length == stable
    assert later.block_ids[:stable] == first.block_ids[:stable]
    assert later.prefix_digests[:stable] == first.prefix_digests[:stable]
    # the new block did land inside the volatile tail, which is what makes the
    # stable-prefix guarantee non-trivial here
    assert later.block_ids[stable] == "history-0-inserted"


def test_ordering_does_not_depend_on_the_order_the_caller_supplied_blocks() -> None:
    """Two callers building the same set differently must produce the same prompt."""

    forwards = plan(standard_blocks())
    backwards = plan(tuple(reversed(standard_blocks())))
    assert backwards.block_ids == forwards.block_ids
    assert backwards.prefix_digests == forwards.prefix_digests
    assert backwards.plan_digest == forwards.plan_digest


def test_a_reordered_prefix_is_rejected_not_tolerated() -> None:
    """The wrong answer is caught: changing a leading block changes every digest after it."""

    original = plan(standard_blocks())
    mutated_blocks = list(standard_blocks())
    mutated_blocks[0] = ContextBlock(
        block_id="sys-prompt", role=BlockRole.SYSTEM, kind=BlockKind.SYSTEM,
        stability_class=StabilityClass.IMMUTABLE,
        digest="sha256:" + "f" * 64,  # one byte of the system prompt changed
        token_cost=100, required=True, snapshot_sha=SNAPSHOT_SHA,
    )
    mutated = plan(tuple(mutated_blocks))
    assert mutated.block_ids == original.block_ids
    assert mutated.prefix_digests[0] != original.prefix_digests[0]
    assert all(left != right for left, right
               in zip(mutated.prefix_digests, original.prefix_digests, strict=True))


def test_a_required_block_is_never_evicted() -> None:
    """A truncated system prompt produces a confident wrong answer; refuse instead."""

    blocks = standard_blocks()
    required_cost = sum(item.token_cost or 0 for item in blocks if item.required)
    assert required_cost == 160

    with pytest.raises(KernelError) as excinfo:
        plan(blocks, budget_tokens=required_cost - 1)
    assert excinfo.value.code == "BUDGET_EXHAUSTED"
    assert excinfo.value.retryable is False
    assert excinfo.value.details["requiredTokens"] == required_cost
    assert sorted(excinfo.value.details["requiredBlockIds"]) == [
        "spec-1", "sys-prompt", "task-current"]

    # exactly the required floor fits, and only optional blocks are dropped
    tight = plan(blocks, budget_tokens=required_cost)
    assert sorted(tight.block_ids) == ["spec-1", "sys-prompt", "task-current"]
    assert all(item.required for item in tight.blocks)
    assert {item.block_id for item in tight.evictions} == {
        "tools-1", "repo-map-1", "history-1"}


def test_an_unmeasured_token_cost_never_becomes_zero() -> None:
    """A block of unknown size has not been shown to fit anything."""

    blocks = (*standard_blocks(),
              block("mystery", kind=BlockKind.FILE, stability=StabilityClass.SLOW,
                    cost=None))
    result = plan(blocks, budget_tokens=1)

    assert result.token_cost_measured is False
    assert result.total_token_cost is None       # not 0
    assert result.within_budget is None          # not True
    assert result.budget_decision is BudgetDecision.REFUSED_UNMEASURED
    assert result.evictions == ()                # no budget decision was made at all

    payload = result.to_payload()
    assert payload["totalTokenCost"] is None
    assert payload["withinBudget"] is None
    unmeasured = next(row for row in payload["blocks"] if row["blockId"] == "mystery")
    assert unmeasured["tokenCost"] is None
    assert unmeasured["tokenCostMeasured"] is False


def test_a_measured_zero_and_an_unmeasured_cost_do_not_render_alike() -> None:
    """0 is a legal cost; ``None`` is the absence of a measurement."""

    zero = plan((block("empty", cost=0),), budget_tokens=0)
    assert zero.total_token_cost == 0
    assert zero.within_budget is True
    assert zero.budget_decision is BudgetDecision.HONOURED
    assert zero.to_payload()["blocks"][0]["tokenCostMeasured"] is True

    unknown = plan((block("empty", cost=None),), budget_tokens=0)
    assert unknown.total_token_cost is None
    assert unknown.within_budget is None
    assert unknown.budget_decision is BudgetDecision.REFUSED_UNMEASURED


def test_an_injected_counter_measures_what_the_caller_did_not() -> None:
    counter = FixedCounter({"mystery": 7})
    result = plan((block("known", cost=3), block("mystery", cost=None)),
                  budget_tokens=100, counter=counter)
    assert counter.calls == ["mystery"]  # a supplied cost is never re-measured
    assert result.token_cost_measured is True
    assert result.total_token_cost == 10
    assert result.within_budget is True


def test_a_counter_that_cannot_answer_raises_rather_than_returning_a_placeholder() -> None:
    with pytest.raises(KernelError) as excinfo:
        plan((block("mystery", cost=None),), budget_tokens=10, counter=BrokenCounter())
    assert excinfo.value.code == "RETRIEVAL_MISS"


def test_a_counter_returning_a_non_integer_is_refused() -> None:
    class SloppyCounter:
        def count(self, item: ContextBlock) -> int:
            return True  # a bool is an int in Python and must not pass as a count

    with pytest.raises(KernelError) as excinfo:
        plan((block("mystery", cost=None),), counter=SloppyCounter())
    assert excinfo.value.code == "MALFORMED_INPUT"


# --- positive gates ----------------------------------------------------------


def test_gate_within_token_budget() -> None:
    """within-token-budget: eviction is volatile-first and reports what it bought."""

    result = plan(standard_blocks(), budget_tokens=210)
    assert result.total_token_cost is not None and result.total_token_cost <= 210
    assert result.within_budget is True
    assert result.budget_decision is BudgetDecision.HONOURED
    assert [item.block_id for item in result.evictions] == ["history-1", "repo-map-1"]
    assert [item.reason for item in result.evictions] == [
        EvictionReason.BUDGET_EXCEEDED, EvictionReason.BUDGET_EXCEEDED]
    assert result.evictions[0].prefix_disturbed is False   # volatile: cheap
    assert result.evictions[1].prefix_disturbed is True    # slow: cost the cache too


def test_gate_within_token_budget_reports_none_when_no_budget_was_stated() -> None:
    """"No budget" and "a budget of zero" are different observations."""

    unbudgeted = plan(standard_blocks())
    assert unbudgeted.budget_decision is BudgetDecision.NO_BUDGET
    assert unbudgeted.budget_tokens is None
    assert unbudgeted.within_budget is None
    assert unbudgeted.total_token_cost == 250
    assert unbudgeted.evictions == ()


def test_gate_prefix_hash_stable() -> None:
    """prefix-hash-stable: the emitted order never moves backwards in stability."""

    result = plan(standard_blocks())
    assert result.ordering_is_stability_first is True
    assert result.block_ids == (
        "sys-prompt", "spec-1", "tools-1", "repo-map-1", "history-1", "task-current")
    classes = [item.stability_class for item in result.blocks]
    assert classes == [StabilityClass.IMMUTABLE, StabilityClass.IMMUTABLE,
                       StabilityClass.SLOW, StabilityClass.SLOW,
                       StabilityClass.VOLATILE, StabilityClass.VOLATILE]


def test_gate_prefix_hash_stable_places_a_breakpoint_at_every_class_boundary() -> None:
    result = plan(standard_blocks())
    assert [item.index for item in result.cache_breakpoints] == [2, 4]
    first = result.cache_breakpoints[0]
    assert first.before_class is StabilityClass.IMMUTABLE
    assert first.after_class is StabilityClass.SLOW
    assert first.prefix_block_count == 2
    assert first.prefix_digest == result.prefix_digests[1]
    assert result.dropped_breakpoints == 0


def test_gate_prefix_hash_stable_counts_breakpoints_it_had_to_drop() -> None:
    """A provider cap is honoured, and the loss is counted rather than hidden."""

    result = plan(standard_blocks(), breakpoints=1)
    assert len(result.cache_breakpoints) == 1
    assert result.dropped_breakpoints == 1
    assert result.cache_breakpoints[0].index == 4  # the longest prefix survives
    assert DEFAULT_MAX_BREAKPOINTS == 4


def test_gate_critical_state_preserved() -> None:
    """critical-state-preserved: no required block is ever in the eviction report."""

    outputs = handle(base_request(token_budget={"totalTokens": 180}))
    assert outputs["compaction_snapshot"]["requiredBlockEvicted"] is False
    assert outputs["gates"]["critical-state-preserved"] is True
    assert sorted(outputs["compaction_snapshot"]["retainedBlockIds"]) == [
        "skill:planner", "spec:spec-1", "step:step-1"]
    assert outputs["compaction_snapshot"]["droppedBlockIds"] == ["repo:index-1"]
    assert outputs["compaction_snapshot"]["reclaimedTokens"] == 30
    assert outputs["compaction_snapshot"]["reclaimedTokensMeasured"] is True


def test_gate_retrieval_trace_complete() -> None:
    """retrieval-trace-complete: every retrieved block is accounted for either way."""

    outputs = handle(base_request(token_budget={"totalTokens": 180}))
    trace = {row["blockId"]: row for row in outputs["retrieval_trace"]}
    assert set(trace) == {"skill:planner", "spec:spec-1", "repo:index-1", "step:step-1"}
    assert trace["repo:index-1"]["disposition"] == "evicted"
    assert trace["repo:index-1"]["reason"] == "budget-exceeded"
    assert trace["spec:spec-1"]["disposition"] == "included"
    assert trace["spec:spec-1"]["reason"] == "retained"
    assert outputs["gates"]["retrieval-trace-complete"] is True


def test_gate_retrieval_trace_complete_refuses_a_missing_required_block() -> None:
    """A block the caller declared essential and did not retrieve is a RETRIEVAL_MISS."""

    with pytest.raises(KernelError) as excinfo:
        plan(standard_blocks(), must_include=("spec-1", "never-retrieved"))
    assert excinfo.value.code == "RETRIEVAL_MISS"
    assert excinfo.value.details["missingBlockIds"] == ["never-retrieved"]
    assert excinfo.value.retryable is True


# --- invariants --------------------------------------------------------------


def test_invariant_i1_context_never_mixes_two_snapshots() -> None:
    """I1: a prompt describing two repository states describes neither."""

    with pytest.raises(KernelError) as excinfo:
        plan((block("a", snapshot_sha=SNAPSHOT_SHA),
              block("b", snapshot_sha=OTHER_SHA)))
    assert excinfo.value.code == "CONTEXT_SNAPSHOT_MIXED"
    assert excinfo.value.details["snapshotShas"] == sorted([SNAPSHOT_SHA, OTHER_SHA])
    assert excinfo.value.retryable is False

    # blocks with no snapshot binding (a system prompt, a tool schema) are fine
    plan((block("a", snapshot_sha=SNAPSHOT_SHA), block("b", snapshot_sha="")))


def test_invariant_i2_repository_content_may_not_occupy_the_system_role() -> None:
    """I2: repository text is data, and the system role is the escalation it wants."""

    assert UNTRUSTED_KINDS == {BlockKind.REPO_MAP, BlockKind.FILE}
    for kind in sorted(UNTRUSTED_KINDS, key=lambda item: item.value):
        with pytest.raises(KernelError) as excinfo:
            block("hostile", role=BlockRole.SYSTEM, kind=kind)
        assert excinfo.value.code == "PROMPT_INJECTION_RISK"
        assert excinfo.value.details["kind"] == str(kind)

    # the same content in a user role is allowed
    assert block("fine", role=BlockRole.USER, kind=BlockKind.FILE).role is BlockRole.USER


def test_invariant_i3_the_context_ledger_is_structured_and_content_free() -> None:
    """I3: the ledger carries digests and classes, never bytes."""

    outputs = handle(base_request())
    ledger = outputs["context_ledger"]
    assert ledger["contentFree"] is True
    assert ledger["blockCount"] == 4
    assert ledger["digest"].startswith("sha256:")
    for entry in ledger["entries"]:
        assert set(entry) == {"blockId", "kind", "stabilityClass", "digest", "tokenCost"}
    assert "text" not in str(ledger) and "content" not in str(ledger).replace(
        "contentFree", "")


def test_invariant_i4_a_plan_carries_digests_rather_than_the_bytes_it_addresses() -> None:
    """I4: nothing a planner emits can leak a secret it never held."""

    secret_bearing = block("env-file", kind=BlockKind.FILE)
    payload = plan((secret_bearing,)).to_payload()
    assert set(payload["blocks"][0]) == {
        "blockId", "role", "kind", "stabilityClass", "digest", "tokenCost",
        "tokenCostMeasured", "required", "snapshotSha",
    }
    assert payload["blocks"][0]["digest"] == secret_bearing.digest


# --- mandatory negatives -----------------------------------------------------


def test_negative_malformed_input_is_rejected() -> None:
    """malformed-input-is-rejected: unknown fields, empty input, wrong types."""

    with pytest.raises(KernelError) as unknown:
        handle(base_request(bogusField=1))
    assert unknown.value.code == "UNKNOWN_FIELD"

    with pytest.raises(KernelError) as empty:
        handle({})
    assert empty.value.code == "MISSING_REQUIRED_INPUT"

    with pytest.raises(KernelError) as no_spec:
        handle(base_request(task_spec=None))
    assert no_spec.value.code == "MISSING_REQUIRED_INPUT"

    with pytest.raises(KernelError) as unknown_block_field:
        handle(base_request(blocks=[{
            "blockId": "b", "role": "user", "kind": "file", "stabilityClass": "slow",
            "digest": "sha256:" + "9" * 64, "surprise": True}]))
    assert unknown_block_field.value.code == "UNKNOWN_FIELD"

    with pytest.raises(KernelError) as bad_enum:
        handle(base_request(blocks=[{
            "blockId": "b", "role": "root", "kind": "file", "stabilityClass": "slow",
            "digest": "sha256:" + "9" * 64}]))
    assert bad_enum.value.code == "MALFORMED_INPUT"

    with pytest.raises(KernelError) as not_a_block:
        plan(("just a string",))  # type: ignore[arg-type]
    assert not_a_block.value.code == "MALFORMED_INPUT"


def test_negative_stale_snapshot_is_rejected() -> None:
    """stale-snapshot-is-rejected: a block bound to another snapshot cannot join."""

    result = dispatch(SKILL_ID, base_request(blocks=[{
        "blockId": "stale-file", "role": "user", "kind": "file",
        "stabilityClass": "slow", "digest": "sha256:" + "9" * 64,
        "snapshotSha": OTHER_SHA}]))
    assert result.status is Status.FAILED
    assert result.error["code"] == "CONTEXT_SNAPSHOT_MIXED"


def test_negative_unauthorized_tool_is_denied() -> None:
    """unauthorized-tool-is-denied: an untrusted block cannot claim the system role."""

    result = dispatch(SKILL_ID, base_request(blocks=[{
        "blockId": "readme", "role": "system", "kind": "file",
        "stabilityClass": "slow", "digest": "sha256:" + "9" * 64,
        "snapshotSha": SNAPSHOT_SHA}]))
    assert result.status is Status.FAILED
    assert result.error["code"] == "PROMPT_INJECTION_RISK"
    assert result.error["category"] == "policy"


def test_negative_interrupted_is_not_success() -> None:
    """interrupted-is-not-success: a tokeniser that died yields no budget verdict."""

    result = plan(standard_blocks() + (block("mystery", cost=None),), budget_tokens=10)
    assert result.budget_decision is BudgetDecision.REFUSED_UNMEASURED
    assert result.within_budget is not True
    assert result.within_budget is None
    assert result.to_payload()["budgetDecision"] == "REFUSED_UNMEASURED"


def test_negative_partial_is_not_success() -> None:
    """partial-is-not-success: an evicted plan says what it lost, in the same answer."""

    outputs = handle(base_request(token_budget={"totalTokens": 180}))
    assert outputs["gates"]["within-token-budget"] is True
    assert outputs["eviction_report"] != []
    assert outputs["eviction_report"][0]["blockId"] == "repo:index-1"
    assert outputs["eviction_report"][0]["reason"] == "budget-exceeded"
    # a plan that could not be produced at all raises rather than returning a stub
    result = dispatch(SKILL_ID, base_request(token_budget={"totalTokens": 1}))
    assert result.status is Status.FAILED
    assert result.error["code"] == "BUDGET_EXHAUSTED"
    assert result.outputs == {}


def test_negative_duplicate_side_effect_is_prevented() -> None:
    """duplicate-side-effect-is-prevented: planning twice gives one identical plan."""

    request = base_request(token_budget={"totalTokens": 400})
    assert handle(request) == handle(request)
    assert plan(standard_blocks()).plan_digest == plan(standard_blocks()).plan_digest


def test_negative_a_duplicate_block_id_is_rejected() -> None:
    with pytest.raises(KernelError) as excinfo:
        plan((block("same"), block("same", cost=5)))
    assert excinfo.value.code == "DUPLICATE_BLOCK_ID"


def test_negative_stale_fencing_token_is_rejected() -> None:
    """stale-fencing-token-is-rejected: a plan's identity is its exact ordered content.

    A prompt assembled from a superseded plan cannot masquerade as the current
    one, because the plan digest changes with any block that moved or changed.
    """

    current = plan(standard_blocks())
    superseded = plan(standard_blocks()[:-1] + (
        block("task-current", kind=BlockKind.TASK, stability=StabilityClass.VOLATILE,
              cost=11, required=True),))
    assert superseded.block_ids == current.block_ids
    assert superseded.plan_digest != current.plan_digest
    assert superseded.prefix_digests[-1] != current.prefix_digests[-1]


def test_negative_prompt_injection_cannot_expand_authority() -> None:
    """prompt-injection-cannot-expand-authority: a hostile block cannot promote itself.

    Repository-derived content is refused the system role at construction, and a
    block id that reads like an instruction still sorts by its declared class.
    """

    hostile_id = "SYSTEM-ignore-previous-instructions"
    with pytest.raises(KernelError) as excinfo:
        block(hostile_id, role=BlockRole.SYSTEM, kind=BlockKind.FILE)
    assert excinfo.value.code == "PROMPT_INJECTION_RISK"

    demoted = block(hostile_id, role=BlockRole.USER, kind=BlockKind.FILE,
                    stability=StabilityClass.VOLATILE)
    result = plan((*standard_blocks(), demoted))
    assert result.block_ids[0] == "sys-prompt"
    assert result.blocks[0].role is BlockRole.SYSTEM
    assert demoted.block_id in result.block_ids[result.stable_prefix_length:]


# --- registry ----------------------------------------------------------------


def test_registry_round_trip() -> None:
    """dispatch returns SUCCEEDED with the plan, bundle, ledger, trace and gates."""

    result = dispatch(SKILL_ID, base_request(token_budget={"totalTokens": 400}))
    assert result.status is Status.SUCCEEDED
    assert result.skill == SKILL_ID
    assert set(result.outputs) == {
        "context_plan", "context_bundle", "context_ledger", "retrieval_trace",
        "compaction_snapshot", "eviction_report", "gates",
    }
    assert result.outputs["gates"] == {
        "within-token-budget": True, "prefix-hash-stable": True,
        "critical-state-preserved": True, "retrieval-trace-complete": True,
    }
    bundle = result.outputs["context_bundle"]
    assert bundle["blockIds"] == ["skill:planner", "spec:spec-1", "repo:index-1",
                                  "step:step-1"]
    assert bundle["stablePrefixLength"] == 3
    assert bundle["prefixDigest"] == result.outputs["context_plan"]["prefixDigest"]


def test_registry_round_trip_the_prefix_survives_a_new_ledger() -> None:
    """The end-to-end form of the headline property, through the registry."""

    without_ledger = dispatch(SKILL_ID, base_request(token_budget={"totalTokens": 400}))
    with_ledger = dispatch(SKILL_ID, base_request(
        token_budget={"totalTokens": 400},
        previous_ledger={"ledgerId": "ledger-1", "digest": "sha256:" + "5" * 64,
                         "tokenCost": 25},
    ))
    assert with_ledger.status is Status.SUCCEEDED
    stable = without_ledger.outputs["context_bundle"]["stablePrefixLength"]
    first = without_ledger.outputs["context_plan"]["prefixDigests"][:stable]
    second = with_ledger.outputs["context_plan"]["prefixDigests"][:stable]
    assert first == second
    assert with_ledger.outputs["context_bundle"]["blockIds"][:stable] == \
           without_ledger.outputs["context_bundle"]["blockIds"][:stable]
