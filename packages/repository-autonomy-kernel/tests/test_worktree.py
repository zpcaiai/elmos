"""Multi-agent worktree coordinator: gates, invariants and mandatory negatives.

Test names follow the gate / negative-test ids in
``skills/multi-agent-worktree-coordinator/acceptance.yaml``.  Two properties are
pinned above all others: ``src/a/**`` overlaps ``src/a/b.py`` and does *not*
overlap ``src/ab/c.py`` (the string-prefix version of this check is a real bug,
and the test proves it is absent), and a wave whose leasing fails part-way
releases every lease it had already taken.  Nothing here sleeps, touches the
network or reads the wall clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest

from elmos_autonomy_kernel.adapters.memory import FixedClock, InMemoryLeaseStore
from elmos_autonomy_kernel.contracts import Status
from elmos_autonomy_kernel.errors import KernelError
from elmos_autonomy_kernel.leasing import LeaseManager
from elmos_autonomy_kernel.registry import dispatch
from elmos_autonomy_kernel.worktree import (
    RUN_STATES,
    Agent,
    AgentContract,
    AgentRun,
    ArtifactContract,
    ArtifactHandoff,
    PathClaim,
    WorktreeTask,
    assert_merge_passed,
    assign,
    build_merge_plan,
    handle,
    plan_waves,
    validate_agent_contract,
    verify_handoffs,
    verify_merge,
)

SKILL_ID = "multi-agent-worktree-coordinator"
SNAPSHOT_SHA = "sha256:" + "a" * 64
OTHER_SHA = "sha256:" + "b" * 64
DIGEST_A = "sha256:" + "1" * 64
DIGEST_B = "sha256:" + "2" * 64


# --- fixtures ----------------------------------------------------------------


def claim(path_glob: str, mode: str = "write") -> PathClaim:
    return PathClaim(path_glob=path_glob, mode=mode)


def task(task_id: str, *globs: str, role: str = "coder", mode: str = "write",
         depends_on: Sequence[str] = (), worktree_id: str = "",
         tools: Sequence[str] = (), produces: Sequence[str] = (),
         consumes: Sequence[str] = ()) -> WorktreeTask:
    return WorktreeTask(
        task_id=task_id, role=role,
        claims=tuple(claim(item, mode) for item in globs),
        depends_on=tuple(depends_on), worktree_id=worktree_id,
        required_tools=tuple(tools), produces=tuple(produces), consumes=tuple(consumes),
    )


def contract(agent_id: str, *, roles: Sequence[str] = ("coder",),
             scopes: Sequence[PathClaim] = (), tools: Sequence[str] = ()) -> AgentContract:
    return AgentContract(
        agent_id=agent_id, roles=tuple(roles),
        path_scopes=tuple(scopes or (claim("src/**"),)),
        allowed_tools=tuple(tools),
    )


@pytest.fixture()
def manager(clock: FixedClock, leases: InMemoryLeaseStore) -> LeaseManager:
    return LeaseManager(leases, clock)


class FailingLeaseStore:
    """A store that refuses one named resource, to provoke a mid-wave failure."""

    def __init__(self, inner: InMemoryLeaseStore, fail_on: str) -> None:
        self.inner = inner
        self.fail_on = fail_on
        self.released: list[str] = []

    def acquire(self, resource_id: str, owner_id: str, *, ttl_seconds: int):
        if resource_id == self.fail_on:
            raise KernelError(
                code="LEASE_HELD_BY_OTHER",
                message=f"{resource_id!r} is leased by another coordinator",
                retryable=True,
                recommended_action="wait for expiry",
            )
        return self.inner.acquire(resource_id, owner_id, ttl_seconds=ttl_seconds)

    def renew(self, resource_id: str, owner_id: str, fencing_token: int, *, ttl_seconds: int):
        return self.inner.renew(resource_id, owner_id, fencing_token, ttl_seconds=ttl_seconds)

    def release(self, resource_id: str, owner_id: str, fencing_token: int) -> None:
        self.released.append(resource_id)
        self.inner.release(resource_id, owner_id, fencing_token)

    def current_token(self, resource_id: str) -> int:
        return self.inner.current_token(resource_id)


def base_request(lease_store: Any, clock: FixedClock, **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "task_dag": {
            "snapshotSha": SNAPSHOT_SHA,
            "tasks": [
                {"taskId": "t-a", "role": "coder", "requiredTools": ["edit"],
                 "claims": [{"pathGlob": "src/a/**", "mode": "write"}]},
                {"taskId": "t-b", "role": "coder", "requiredTools": ["edit"],
                 "claims": [{"pathGlob": "src/ab/c.py", "mode": "write"}]},
                {"taskId": "t-c", "role": "coder", "requiredTools": ["edit"],
                 "claims": [{"pathGlob": "src/a/b.py", "mode": "write"}]},
            ],
        },
        "agent_contracts": [
            {"agentId": "agent-1", "roles": ["coder"], "allowedTools": ["edit"],
             "pathScopes": [{"pathGlob": "src/**", "mode": "write"}]},
            {"agentId": "agent-2", "roles": ["coder"], "allowedTools": ["edit"],
             "pathScopes": [{"pathGlob": "src/**", "mode": "write"}]},
        ],
        "workspace_topology": {
            "snapshotSha": SNAPSHOT_SHA,
            "leaseTtlSeconds": 900,
            "agents": [{"agentId": "agent-1", "roles": ["coder"]},
                       {"agentId": "agent-2", "roles": ["coder"]}],
        },
        "ports": {"lease_store": lease_store, "clock": clock},
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(request.get(key), dict):
            request[key] = {**request[key], **value}
        else:
            request[key] = value
    return request


# --- the headline overlap property -------------------------------------------


def test_a_directory_glob_overlaps_a_file_inside_it_but_not_a_sibling_prefix() -> None:
    """``src/a/**`` covers ``src/a/b.py`` and must not touch ``src/ab/c.py``.

    ``"src/ab/c.py".startswith("src/a")`` is true, so a string-prefix overlap
    check reports a collision that does not exist and serialises two independent
    tasks.  Comparison happens component by component, so it does not.
    """

    directory = claim("src/a/**")
    inside = claim("src/a/b.py")
    sibling = claim("src/ab/c.py")

    assert directory.overlaps(inside) is True
    assert inside.overlaps(directory) is True
    assert directory.overlaps(sibling) is False
    assert sibling.overlaps(directory) is False

    # the string-prefix bug would have used exactly this value
    assert directory.fixed_prefix == ("src", "a")
    assert "src/ab/c.py".startswith("/".join(directory.fixed_prefix))


def test_the_component_intersection_is_exact_in_both_directions() -> None:
    """The mirror-image bug — reporting two colliding claims as safe — is absent too."""

    assert claim("src/*.py").overlaps(claim("src/b.py")) is True
    assert claim("src/*.py").overlaps(claim("src/b.md")) is False
    assert claim("src/**/*.py").overlaps(claim("src/a/b/c.py")) is True
    assert claim("src/a/*").overlaps(claim("src/a/b/c.py")) is False  # * stays in one component
    assert claim("src/a").overlaps(claim("src/ab")) is False
    assert claim("**").overlaps(claim("anything/at/all.py")) is True
    assert claim("docs/**").overlaps(claim("src/a/b.py")) is False


def test_two_readers_of_one_path_do_not_conflict_but_a_reader_and_a_writer_do() -> None:
    """A reader concurrent with a writer sees a torn tree, which is worse than a refusal."""

    reader = claim("src/a/**", "read")
    other_reader = claim("src/a/b.py", "read")
    writer = claim("src/a/b.py", "write")

    assert reader.overlaps(other_reader) is True
    assert reader.conflicts_with(other_reader) is False
    assert reader.conflicts_with(writer) is True
    assert writer.conflicts_with(reader) is True


def test_a_claim_the_coordinator_cannot_compare_exactly_is_rejected() -> None:
    """Guessing an overlap answer is how a worktree gets corrupted."""

    for bad, code in (("/etc/passwd", "MALFORMED_INPUT"),
                      ("../outside/**", "MALFORMED_INPUT"),
                      ("src\\a\\b.py", "MALFORMED_INPUT"),
                      ("src/[ab]/c.py", "MALFORMED_INPUT"),
                      ("src/a**/b.py", "MALFORMED_INPUT")):
        with pytest.raises(KernelError) as excinfo:
            claim(bad)
        assert excinfo.value.code == code, bad


def test_two_spellings_of_one_claim_are_one_value() -> None:
    assert claim("./src/a/").path_glob == "src/a"
    assert claim("src//a").components == ("src", "a")
    assert claim("./src/a/") == claim("src/a")


# --- the headline rollback property ------------------------------------------


def test_a_partially_acquired_wave_releases_what_it_took(clock: FixedClock) -> None:
    """A half-held wave strands leases on a coordinator that has already given up."""

    inner = InMemoryLeaseStore(clock)
    store = FailingLeaseStore(inner, fail_on="wt-t-b")
    plan = plan_waves([task("t-a", "src/a/**"), task("t-b", "src/b/**")])
    wave = plan.waves[0]
    assert wave.task_ids == ("t-a", "t-b")

    with pytest.raises(KernelError) as excinfo:
        assign(wave, [Agent("agent-1", ("coder",)), Agent("agent-2", ("coder",))],
               LeaseManager(store, clock))
    assert excinfo.value.code == "AGENT_CONFLICT"
    assert excinfo.value.details["releasedLeases"] == 1
    assert excinfo.value.details["cause"] == "LEASE_HELD_BY_OTHER"
    assert excinfo.value.retryable is True

    assert store.released == ["wt-t-a"]
    # the released worktree is genuinely free: a different owner can take it
    granted = inner.acquire("wt-t-a", "someone-else", ttl_seconds=60)
    assert granted["ownerId"] == "someone-else"
    assert granted["fencingToken"] == 2  # tokens stay monotonic across the rollback


def test_a_wave_that_leases_cleanly_holds_exactly_one_lease_per_worktree(
        clock: FixedClock, leases: InMemoryLeaseStore, manager: LeaseManager) -> None:
    plan = plan_waves([task("t-a", "src/a/**"), task("t-b", "src/b/**")])
    result = assign(plan.waves[0], [Agent("agent-1", ("coder",)), Agent("agent-2", ("coder",))],
                    manager)
    assert result.status is Status.SUCCEEDED
    assert [item.task_id for item in result.assignments] == ["t-a", "t-b"]
    assert {item.worktree_id for item in result.assignments} == {"wt-t-a", "wt-t-b"}
    assert all(item.fencing_token == 1 for item in result.assignments)
    assert leases.current_token("wt-t-a") == 1
    assert leases.current_token("wt-t-b") == 1


# --- positive gates ----------------------------------------------------------


def test_gate_write_set_conflict_free() -> None:
    """write-set-conflict-free: no two tasks in a wave share a writable path."""

    plan = plan_waves([
        task("t-a", "src/a/**"), task("t-b", "src/ab/c.py"), task("t-c", "src/a/b.py"),
    ])
    assert [wave.task_ids for wave in plan.waves] == [("t-a", "t-b"), ("t-c",)]
    assert plan.waves[0].write_set == ("src/a/**", "src/ab/c.py")
    for wave in plan.waves:
        for index, left in enumerate(wave.tasks):
            for right in wave.tasks[index + 1:]:
                assert left.conflicts_with(right) is False


def test_gate_write_set_conflict_free_names_the_two_globs_it_objected_to() -> None:
    """A conflict report that cannot name the claims is not reviewable."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-c", "src/a/b.py")])
    assert len(plan.conflicts) == 1
    conflict = plan.conflicts[0]
    assert (conflict.left_task, conflict.right_task) == ("t-a", "t-c")
    assert (conflict.left_glob, conflict.right_glob) == ("src/a/**", "src/a/b.py")
    assert conflict.reason == "overlapping write claim"
    assert conflict.separated is True
    assert plan.wave_of("t-a") != plan.wave_of("t-c")


def test_gate_write_set_conflict_free_is_deterministic() -> None:
    """Two callers with the same task set in different orders get identical waves."""

    tasks = [task("t-a", "src/a/**"), task("t-b", "src/ab/c.py"), task("t-c", "src/a/b.py")]
    forwards = plan_waves(tasks)
    backwards = plan_waves(list(reversed(tasks)))
    assert backwards.to_payload() == forwards.to_payload()
    assert backwards.to_payload()["digest"] == forwards.to_payload()["digest"]


def test_gate_agent_contract_valid() -> None:
    """agent-contract-valid: the contract must cover role, tools and every claim."""

    coder = contract("agent-1", scopes=(claim("src/**"),), tools=("edit",))
    validate_agent_contract(coder, task("t-a", "src/a/b.py", tools=("edit",)))
    assert coder.covers(task("t-a", "src/a/b.py", tools=("edit",))) is None


def test_gate_agent_contract_valid_rejects_a_claim_outside_the_scope() -> None:
    """The wrong answer is rejected: a claim the contract does not cover is refused."""

    coder = contract("agent-1", scopes=(claim("src/a/**"),), tools=("edit",))
    with pytest.raises(KernelError) as excinfo:
        validate_agent_contract(coder, task("t-x", "src/ab/c.py", tools=("edit",)))
    assert excinfo.value.code == "AGENT_CONTRACT_INVALID"
    assert "lies outside the agent's path scopes" in excinfo.value.details["reason"]

    with pytest.raises(KernelError) as wrong_role:
        validate_agent_contract(coder, task("t-x", "src/a/b.py", role="reviewer",
                                            tools=("edit",)))
    assert wrong_role.value.code == "AGENT_CONTRACT_INVALID"

    with pytest.raises(KernelError) as ungranted_tool:
        validate_agent_contract(coder, task("t-x", "src/a/b.py", tools=("shell",)))
    assert ungranted_tool.value.code == "AGENT_CONTRACT_INVALID"


def test_an_empty_agent_contract_collection_is_a_deny_not_a_wildcard() -> None:
    """"No declared capability" resolving to "any capability" is default-allow."""

    empty = AgentContract(agent_id="agent-1")
    assert empty.roles == () and empty.path_scopes == () and empty.allowed_tools == ()
    assert empty.network == "deny"
    assert empty.covers(task("t-a", "src/a/b.py")) is not None
    assert Agent("agent-1").can_take("coder") is False


def test_a_read_scope_never_authorises_a_write(clock: FixedClock) -> None:
    """The one direction that must be impossible."""

    reader = AgentContract(agent_id="agent-1", roles=("coder",),
                           path_scopes=(claim("src/**", "read"),))
    assert reader.covers(task("t-a", "src/a/b.py", mode="read")) is None
    assert reader.covers(task("t-a", "src/a/b.py", mode="write")) is not None


def test_gate_handoff_schema_valid() -> None:
    """handoff-schema-valid: schema and digest must both match what was produced."""

    handoff = ArtifactHandoff(artifact_id="art-1", producer_task_id="t-a",
                              consumer_task_id="t-b", schema_id="schema-v1",
                              content_digest=DIGEST_A)
    verified = verify_handoffs(
        (handoff,), {"art-1": ArtifactContract("art-1", "schema-v1")}, {"art-1": DIGEST_A})
    assert verified[0]["verified"] is True
    assert verified[0]["artifactId"] == "art-1"


def test_gate_handoff_schema_valid_rejects_a_plausible_but_different_artifact() -> None:
    """A digest mismatch is the case where the consumer reads the wrong file."""

    handoff = ArtifactHandoff(artifact_id="art-1", producer_task_id="t-a",
                              consumer_task_id="t-b", schema_id="schema-v1",
                              content_digest=DIGEST_A)
    with pytest.raises(KernelError) as excinfo:
        verify_handoffs((handoff,), {"art-1": ArtifactContract("art-1", "schema-v1")},
                        {"art-1": DIGEST_B})
    assert excinfo.value.code == "HANDOFF_MISMATCH"
    assert excinfo.value.details == {"artifactId": "art-1", "declared": DIGEST_A,
                                     "actual": DIGEST_B}


def test_gate_handoff_schema_valid_refuses_an_undeclared_or_unproduced_artifact() -> None:
    handoff = ArtifactHandoff(artifact_id="art-1", producer_task_id="t-a",
                              consumer_task_id="t-b", schema_id="schema-v1",
                              content_digest=DIGEST_A)
    with pytest.raises(KernelError) as undeclared:
        verify_handoffs((handoff,), {}, {"art-1": DIGEST_A})
    assert undeclared.value.code == "HANDOFF_MISMATCH"
    assert "no declared artifact contract" in undeclared.value.message

    with pytest.raises(KernelError) as unproduced:
        verify_handoffs((handoff,), {"art-1": ArtifactContract("art-1", "schema-v1")}, {})
    assert unproduced.value.code == "HANDOFF_MISMATCH"
    assert "never produced" in unproduced.value.message

    with pytest.raises(KernelError) as wrong_schema:
        verify_handoffs((handoff,), {"art-1": ArtifactContract("art-1", "schema-v2")},
                        {"art-1": DIGEST_A})
    assert wrong_schema.value.code == "HANDOFF_MISMATCH"
    assert wrong_schema.value.details["contracted"] == "schema-v2"


def test_gate_integration_merge_pass() -> None:
    """integration-merge-pass: merge order follows waves, then task id."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-b", "src/ab/c.py"),
                       task("t-c", "src/a/b.py")])
    merge_plan = build_merge_plan(plan)
    assert merge_plan.order == ("t-a", "t-b", "t-c")
    assert merge_plan.wave_of == {"t-a": 0, "t-b": 0, "t-c": 1}
    assert merge_plan.write_sets["t-a"] == ("src/a/**",)

    runs = tuple(AgentRun(task_id=task_id, agent_id="agent-1", worktree_id=f"wt-{task_id}",
                          wave_index=merge_plan.wave_of[task_id], state="succeeded",
                          fencing_token=1)
                 for task_id in merge_plan.order)
    verification = verify_merge(merge_plan, runs)
    assert verification.passed is True
    assert verification.merged == ("t-a", "t-b", "t-c")
    assert_merge_passed(verification)


def test_gate_integration_merge_pass_blocks_every_non_success_state_by_name() -> None:
    """``partial``, ``interrupted`` and ``failed`` are three different blockers."""

    plan = plan_waves([task("t-a", "src/a/**")])
    merge_plan = build_merge_plan(plan)
    expected = {"partial": "AGENT_PARTIAL", "interrupted": "AGENT_PARTIAL",
                "failed": "MERGE_VERIFICATION_FAILED",
                "running": "MERGE_VERIFICATION_FAILED"}
    assert set(RUN_STATES) == set(expected) | {"succeeded"}
    for state, code in expected.items():
        run = AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a",
                       wave_index=0, state=state, fencing_token=1)
        verification = verify_merge(merge_plan, (run,))
        assert verification.passed is False, state
        assert verification.merged == ()
        assert verification.blocked[0]["code"] == code, state
        assert run.succeeded is False


def test_gate_integration_merge_pass_blocks_when_handoffs_were_not_verified() -> None:
    plan = plan_waves([task("t-a", "src/a/**")])
    merge_plan = build_merge_plan(plan)
    run = AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a",
                   wave_index=0, state="succeeded", fencing_token=1)
    verification = verify_merge(merge_plan, (run,), handoffs_verified=False)
    assert verification.passed is False
    assert verification.blocked[0]["code"] == "HANDOFF_MISMATCH"
    with pytest.raises(KernelError) as excinfo:
        assert_merge_passed(verification)
    assert excinfo.value.code == "MERGE_VERIFICATION_FAILED"
    assert excinfo.value.partial is True  # one task did merge; that is not lost


# --- invariants --------------------------------------------------------------


def test_invariant_i1_the_plan_is_data_not_a_conversation() -> None:
    """I1: natural-language coordination is not the state; the plan is, and it hashes."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-c", "src/a/b.py")])
    payload = plan.to_payload()
    assert payload["waveCount"] == 2
    assert payload["taskCount"] == 2
    assert payload["digest"].startswith("sha256:")
    assert payload["conflicts"][0]["reason"] == "overlapping write claim"
    assert plan_waves(list(plan.waves[0].tasks) + list(plan.waves[1].tasks)
                      ).to_payload()["digest"] == payload["digest"]


def test_invariant_i2_one_writer_per_file_at_a_time(
        clock: FixedClock, manager: LeaseManager) -> None:
    """I2: a task colliding with a still-running earlier task is not dispatched."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-c", "src/a/b.py")])
    running = (AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a",
                        wave_index=0, state="running", fencing_token=1,
                        claims=(claim("src/a/**"),)),)
    result = assign(plan.waves[1], [Agent("agent-2", ("coder",))], manager, running=running)
    assert result.assignments == ()
    assert result.unassigned[0].task_id == "t-c"
    assert result.unassigned[0].code == "AGENT_CONFLICT"
    assert "still held by running task 't-a'" in result.unassigned[0].reason
    assert result.status is Status.PARTIAL


def test_invariant_i2_a_settled_earlier_task_no_longer_blocks(
        clock: FixedClock, manager: LeaseManager) -> None:
    """Wave membership bounds what may *start*; a finished run reserves nothing."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-c", "src/a/b.py")])
    settled = (AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a",
                        wave_index=0, state="succeeded", fencing_token=1,
                        claims=(claim("src/a/**"),)),)
    result = assign(plan.waves[1], [Agent("agent-2", ("coder",))], manager, running=settled)
    assert [item.task_id for item in result.assignments] == ["t-c"]
    assert result.status is Status.SUCCEEDED


def test_invariant_i2_two_tasks_sharing_a_worktree_are_serialised() -> None:
    """One checkout is one writer, even when the claims are disjoint."""

    plan = plan_waves([task("t-a", "src/a/**", worktree_id="wt-shared"),
                       task("t-b", "docs/**", worktree_id="wt-shared")])
    assert [wave.task_ids for wave in plan.waves] == [("t-a",), ("t-b",)]
    assert plan.conflicts[0].reason == "shared worktree"


def test_invariant_i3_a_sub_agent_result_is_verified_before_it_merges() -> None:
    """I3: an unverified handoff never becomes an input to the integration branch."""

    plan = plan_waves([task("t-a", "src/a/**", produces=("art-1",))])
    merge_plan = build_merge_plan(plan)
    run = AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a",
                   wave_index=0, state="succeeded", fencing_token=1)
    assert verify_merge(merge_plan, (run,), handoffs_verified=True).passed is True
    assert verify_merge(merge_plan, (run,), handoffs_verified=False).passed is False


def test_invariant_i4_reaching_a_limit_returns_partial(
        clock: FixedClock, manager: LeaseManager) -> None:
    """I4: capped parallelism reports the tasks it did not start, and is PARTIAL."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-b", "src/b/**"),
                       task("t-d", "src/d/**")])
    wave = plan.waves[0]
    assert len(wave.tasks) == 3
    result = assign(wave, [Agent(f"agent-{n}", ("coder",)) for n in (1, 2, 3)], manager,
                    max_parallel=2)
    assert result.status is Status.PARTIAL
    assert result.status is not Status.SUCCEEDED
    assert len(result.assignments) == 2
    assert [item.task_id for item in result.unassigned] == ["t-d"]
    assert result.unassigned[0].code == "BUDGET_EXHAUSTED"
    payload = result.to_payload()
    assert payload["status"] == "PARTIAL"
    assert payload["assignedCount"] == 2 and payload["unassignedCount"] == 1


def test_invariant_i4_every_wave_member_appears_in_exactly_one_output_list(
        clock: FixedClock, manager: LeaseManager) -> None:
    """"We ran four of five" can never be rendered as "we ran the wave"."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-b", "src/b/**"),
                       task("t-d", "src/d/**", role="reviewer")])
    wave = plan.waves[0]
    result = assign(wave, [Agent("agent-1", ("coder",)), Agent("agent-2", ("coder",))],
                    manager)
    accounted = ([item.task_id for item in result.assignments]
                 + [item.task_id for item in result.unassigned])
    assert sorted(accounted) == sorted(wave.task_ids)
    assert len(accounted) == len(set(accounted))
    assert result.unassigned[0].code == "WORKTREE_UNAVAILABLE"
    assert result.status is Status.PARTIAL


# --- mandatory negatives -----------------------------------------------------


def test_negative_malformed_input_is_rejected(clock: FixedClock,
                                              leases: InMemoryLeaseStore) -> None:
    """malformed-input-is-rejected: unknown fields, empty input, undeclared write sets."""

    with pytest.raises(KernelError) as unknown:
        handle(base_request(leases, clock, bogusField=1))
    assert unknown.value.code == "UNKNOWN_FIELD"

    with pytest.raises(KernelError) as empty:
        handle({})
    assert empty.value.code == "MISSING_REQUIRED_INPUT"

    with pytest.raises(KernelError) as no_tasks:
        handle(base_request(leases, clock, task_dag={"tasks": []}))
    assert no_tasks.value.code == "MISSING_REQUIRED_INPUT"

    with pytest.raises(KernelError) as no_claims:
        WorktreeTask(task_id="t-a", role="coder", claims=())
    assert no_claims.value.code == "MISSING_REQUIRED_INPUT"
    assert "undeclared write set cannot be checked" in no_claims.value.recommended_action

    with pytest.raises(KernelError) as bad_mode:
        PathClaim(path_glob="src/a", mode="append")
    assert bad_mode.value.code == "MALFORMED_INPUT"

    with pytest.raises(KernelError) as bad_state:
        AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-a", wave_index=0,
                 state="probably-fine", fencing_token=1)
    assert bad_state.value.code == "MALFORMED_INPUT"


def test_negative_stale_snapshot_is_rejected(clock: FixedClock,
                                             leases: InMemoryLeaseStore) -> None:
    """stale-snapshot-is-rejected: a DAG planned against another snapshot cannot run."""

    result = dispatch(SKILL_ID, base_request(
        leases, clock, workspace_topology={"snapshotSha": OTHER_SHA}))
    assert result.status is Status.FAILED
    assert result.error["code"] == "STALE_SNAPSHOT"
    assert result.error["details"] == {"dagSnapshot": SNAPSHOT_SHA,
                                       "workspaceSnapshot": OTHER_SHA}


def test_negative_unauthorized_tool_is_denied(clock: FixedClock,
                                              leases: InMemoryLeaseStore) -> None:
    """unauthorized-tool-is-denied: a task needing an ungranted tool is not dispatched."""

    result = dispatch(SKILL_ID, base_request(leases, clock, task_dag={
        "snapshotSha": SNAPSHOT_SHA,
        "tasks": [{"taskId": "t-a", "role": "coder", "requiredTools": ["shell"],
                   "claims": [{"pathGlob": "src/a/**", "mode": "write"}]}],
    }))
    assert result.status is Status.PARTIAL
    unassigned = result.outputs["agent_assignments"]["unassigned"]
    assert unassigned[0]["taskId"] == "t-a"
    assert unassigned[0]["code"] == "AGENT_CONTRACT_INVALID"
    assert "tool 'shell' is not granted" in unassigned[0]["reason"]


def test_negative_interrupted_is_not_success() -> None:
    """interrupted-is-not-success: an interrupted run never merges."""

    plan = plan_waves([task("t-a", "src/a/**")])
    merge_plan = build_merge_plan(plan)
    run = AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a", wave_index=0,
                   state="interrupted", fencing_token=1)
    assert run.succeeded is False
    verification = verify_merge(merge_plan, (run,))
    assert verification.passed is False
    assert verification.merged == ()
    assert verification.blocked[0]["reason"] == "run state is 'interrupted', which is not " \
                                                "'succeeded'"


def test_negative_partial_is_not_success() -> None:
    """partial-is-not-success: a partial sub-agent result is never folded in."""

    plan = plan_waves([task("t-a", "src/a/**"), task("t-b", "src/b/**")])
    merge_plan = build_merge_plan(plan)
    runs = (
        AgentRun(task_id="t-a", agent_id="agent-1", worktree_id="wt-t-a", wave_index=0,
                 state="succeeded", fencing_token=1),
        AgentRun(task_id="t-b", agent_id="agent-2", worktree_id="wt-t-b", wave_index=0,
                 state="partial", fencing_token=1),
    )
    verification = verify_merge(merge_plan, runs)
    assert verification.merged == ("t-a",)
    assert verification.blocked[0]["code"] == "AGENT_PARTIAL"
    with pytest.raises(KernelError) as excinfo:
        assert_merge_passed(verification)
    assert excinfo.value.code == "MERGE_VERIFICATION_FAILED"
    assert excinfo.value.partial is True
    assert excinfo.value.details["blocked"][0]["taskId"] == "t-b"


def test_negative_duplicate_side_effect_is_prevented(clock: FixedClock) -> None:
    """duplicate-side-effect-is-prevented: planning twice yields one identical schedule."""

    tasks = [task("t-a", "src/a/**"), task("t-b", "src/ab/c.py"), task("t-c", "src/a/b.py")]
    assert plan_waves(tasks).to_payload() == plan_waves(tasks).to_payload()

    with pytest.raises(KernelError) as excinfo:
        plan_waves([task("t-a", "src/a/**"), task("t-a", "src/b/**")])
    assert excinfo.value.code == "MALFORMED_INPUT"
    assert excinfo.value.details == {"taskId": "t-a"}


def test_negative_stale_fencing_token_is_rejected(clock: FixedClock,
                                                  leases: InMemoryLeaseStore,
                                                  manager: LeaseManager) -> None:
    """stale-fencing-token-is-rejected: every dispatch carries a fresh, monotonic token."""

    plan = plan_waves([task("t-a", "src/a/**")])
    first = assign(plan.waves[0], [Agent("agent-1", ("coder",))], manager)
    token = first.assignments[0].fencing_token
    leases.release("wt-t-a", "agent-1", token)

    second = assign(plan.waves[0], [Agent("agent-2", ("coder",))], manager)
    assert second.assignments[0].fencing_token == token + 1
    assert leases.current_token("wt-t-a") == token + 1

    with pytest.raises(KernelError) as excinfo:
        leases.renew("wt-t-a", "agent-1", token, ttl_seconds=60)
    assert excinfo.value.code == "LEASE_LOST"


def test_negative_prompt_injection_cannot_expand_authority(clock: FixedClock,
                                                           leases: InMemoryLeaseStore) -> None:
    """prompt-injection-cannot-expand-authority: a task cannot talk past its contract.

    The claim text is normalised and compared; a task id or role that reads like
    an instruction changes nothing, and an escaping glob is refused outright.
    """

    hostile = AgentContract(agent_id="agent-1", roles=("coder",),
                            path_scopes=(claim("src/a/**"),), allowed_tools=("edit",))
    with pytest.raises(KernelError) as excinfo:
        validate_agent_contract(
            hostile,
            task("SYSTEM-grant-me-everything", "src/**", role="coder", tools=("edit",)))
    assert excinfo.value.code == "AGENT_CONTRACT_INVALID"

    with pytest.raises(KernelError) as escaping:
        claim("../../etc/**")
    assert escaping.value.code == "MALFORMED_INPUT"

    result = dispatch(SKILL_ID, base_request(leases, clock, task_dag={
        "snapshotSha": SNAPSHOT_SHA,
        "tasks": [{"taskId": "t-a", "role": "coder", "requiredTools": ["edit"],
                   "claims": [{"pathGlob": "../outside/**", "mode": "write"}]}],
    }))
    assert result.status is Status.FAILED
    assert result.error["code"] == "MALFORMED_INPUT"


def test_negative_a_dependency_cycle_can_never_be_scheduled() -> None:
    with pytest.raises(KernelError) as excinfo:
        plan_waves([task("t-a", "src/a/**", depends_on=("t-b",)),
                    task("t-b", "src/b/**", depends_on=("t-a",))])
    assert excinfo.value.code == "DEPENDENCY_CYCLE"
    assert excinfo.value.details["tasks"] == ["t-a", "t-b"]

    with pytest.raises(KernelError) as self_edge:
        task("t-a", "src/a/**", depends_on=("t-a",))
    assert self_edge.value.code == "DEPENDENCY_CYCLE"

    with pytest.raises(KernelError) as missing:
        plan_waves([task("t-a", "src/a/**", depends_on=("t-ghost",))])
    assert missing.value.code == "MISSING_REQUIRED_INPUT"


# --- registry ----------------------------------------------------------------


def test_registry_round_trip(clock: FixedClock, leases: InMemoryLeaseStore) -> None:
    """dispatch returns SUCCEEDED with the wave plan, assignments and merge plan."""

    result = dispatch(SKILL_ID, base_request(leases, clock))
    assert result.status is Status.SUCCEEDED
    assert result.skill == SKILL_ID
    assert set(result.outputs) == {
        "wave_plan", "agent_assignments", "agent_runs", "artifact_handoffs",
        "conflict_report", "merge_plan",
    }
    plan = result.outputs["wave_plan"]
    assert [wave["taskIds"] for wave in plan["waves"]] == [["t-a", "t-b"], ["t-c"]]
    assert result.outputs["agent_assignments"]["status"] == "SUCCEEDED"
    assert result.outputs["conflict_report"][0]["leftGlob"] == "src/a/**"
    assert result.outputs["conflict_report"][0]["rightGlob"] == "src/a/b.py"


def test_registry_round_trip_reports_partial_when_a_member_is_not_dispatched(
        clock: FixedClock, leases: InMemoryLeaseStore) -> None:
    """A wave with an unassigned member is PARTIAL, never a shorter success."""

    result = dispatch(SKILL_ID, base_request(leases, clock, budget={"maxParallelAgents": 1}))
    assert result.status is Status.PARTIAL
    assert result.status is not Status.SUCCEEDED
    assert result.succeeded is False
    assignments = result.outputs["agent_assignments"]
    assert assignments["assignedCount"] == 1
    assert assignments["unassigned"][0]["code"] == "BUDGET_EXHAUSTED"
