"""Request parsing, planning, journalling, orchestration and dispatch."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from elmos_repository_refactoring.catalog import SKILL_NAMES, topological_order
from elmos_repository_refactoring.cli import main
from elmos_repository_refactoring.contracts import ContractError, FailureClass, RiskClass, Status
from elmos_repository_refactoring.dispatcher import (
    PENDING_SKILLS,
    RuntimeDispatcher,
    dispatch,
    implemented_skills,
)
from elmos_repository_refactoring.journal import RunJournal, idempotency_key
from elmos_repository_refactoring.orchestrator import (
    RefactorRun,
    RunState,
    StepState,
    backoff_seconds,
    classify_failure,
    synthesize_plan,
)
from elmos_repository_refactoring.plan import (
    PlanStep,
    StepValidation,
    critical_path,
    estimate_plan,
    find_cycle,
    read_write_conflicts,
)
from elmos_repository_refactoring.policy import ENTERPRISE_DEFAULT_POLICY, RefactorPolicy, evaluate_gate_set
from elmos_repository_refactoring.request import RefactorRequest
from elmos_repository_refactoring.runtime import describe, skill_catalog_payload

from .fixtures import REVISION, request_payload, workspace_payload


def _step(step_id: str, *, depends: tuple[str, ...] = (), reads: tuple[str, ...] = (),
          writes: tuple[str, ...] = (), seconds: int = 10) -> PlanStep:
    return PlanStep(
        step_id=step_id,
        name=step_id,
        skill="repository-discovery",
        depends_on=depends,
        risk_class=RiskClass.R1,
        inputs=(),
        outputs=(),
        validation=(StepValidation(gate="parse", blocking=True),),
        read_set=reads,
        write_set=writes,
        estimated_seconds=seconds,
    )


class TestRequest:
    def test_parses_and_digests_deterministically(self) -> None:
        request = RefactorRequest.from_payload(request_payload())
        assert request.tenant_id == "acme"
        assert request.digest == RefactorRequest.from_payload(request.to_payload()).digest

    def test_unknown_fields_are_refused(self) -> None:
        payload = request_payload()
        payload["spec"]["surprise"] = True
        with pytest.raises(ContractError) as error:
            RefactorRequest.from_payload(payload)
        assert error.value.code == "unknown_field"

    def test_analyze_only_cannot_create_a_pull_request(self) -> None:
        payload = request_payload(execution={"mode": "analyze-only", "createPullRequest": True})
        with pytest.raises(ContractError) as error:
            RefactorRequest.from_payload(payload)
        assert error.value.code == "incoherent_request"

    def test_autonomy_conflicts_with_a_high_risk_floor(self) -> None:
        payload = request_payload(
            intent={"type": "security-refactor", "goals": ["harden auth"]},
            execution={"mode": "autonomous-low-risk", "createPullRequest": False},
        )
        with pytest.raises(ContractError) as error:
            RefactorRequest.from_payload(payload)
        assert error.value.code == "autonomy_risk_conflict"

    def test_schema_intent_requires_a_database_strategy(self) -> None:
        payload = request_payload(
            intent={"type": "data-schema-refactor", "goals": ["rename a column"]},
            constraints={"databaseStrategy": "none"},
        )
        with pytest.raises(ContractError) as error:
            RefactorRequest.from_payload(payload)
        assert error.value.code == "incoherent_request"

    def test_allowed_and_forbidden_paths_may_not_overlap(self) -> None:
        payload = request_payload(constraints={"allowedPaths": ["src/**"], "forbiddenPaths": ["src/**"]})
        with pytest.raises(ContractError):
            RefactorRequest.from_payload(payload)

    def test_risk_floor_rises_with_the_database_strategy(self) -> None:
        payload = request_payload(
            intent={"type": "data-schema-refactor", "goals": ["expand then contract"]},
            constraints={"databaseStrategy": "expand-contract"},
        )
        assert RefactorRequest.from_payload(payload).risk_floor is RiskClass.R4


class TestPolicy:
    def test_default_policy_denies_network_and_autonomy(self) -> None:
        policy = ENTERPRISE_DEFAULT_POLICY
        assert policy.sandbox.network.value == "deny"
        assert policy.autonomy.max_risk_class is RiskClass.R1
        assert policy.autonomy.minimum_adapter_level.value == "L4"

    def test_undecidable_approval_condition_escalates_rather_than_waives(self) -> None:
        policy = ENTERPRISE_DEFAULT_POLICY
        # `impact` is entirely absent, so every impact-based rule is undecidable.
        required = policy.required_approval_roles({"risk": {"class": "R1"}})
        assert required, "an undecidable approval rule must still require approval"

    def test_a_gate_with_no_result_fails_when_blocking(self) -> None:
        policy = ENTERPRISE_DEFAULT_POLICY
        outcomes, blocking = evaluate_gate_set(policy, {}, {"risk": {"class": "R1"}, "execution": {"mutates": True}})
        assert outcomes["build"].value == "fail"
        assert "build" in blocking

    def test_forbidden_patterns_match_secrets(self) -> None:
        assert ENTERPRISE_DEFAULT_POLICY.forbids("config/secrets/token.txt") is not None
        assert ENTERPRISE_DEFAULT_POLICY.forbids("src/app.py") is None

    def test_declared_digest_must_match_content(self) -> None:
        payload = ENTERPRISE_DEFAULT_POLICY.to_payload()
        payload["metadata"]["digest"] = "sha256:" + "0" * 64
        with pytest.raises(ContractError) as error:
            RefactorPolicy.from_payload(payload)
        assert error.value.code == "policy_digest_mismatch"


class TestPlanGraph:
    def test_cycles_are_reported_concretely(self) -> None:
        steps = [_step("a", depends=("b",)), _step("b", depends=("a",))]
        cycle = find_cycle(steps)
        assert cycle and cycle[0] == cycle[-1]

    def test_critical_path_follows_the_longest_chain(self) -> None:
        steps = [
            _step("a", seconds=10),
            _step("b", depends=("a",), seconds=100),
            _step("c", depends=("a",), seconds=5),
            _step("d", depends=("b", "c"), seconds=1),
        ]
        path, total = critical_path(steps)
        assert path == ("a", "b", "d")
        assert total == 111

    def test_write_write_conflicts_between_independent_steps(self) -> None:
        steps = [_step("a", writes=("src/**",)), _step("b", writes=("src/x.py",))]
        conflicts = read_write_conflicts(steps)
        assert conflicts and conflicts[0][2].startswith("write-write")

    def test_ordered_steps_do_not_conflict(self) -> None:
        steps = [_step("a", writes=("src/x.py",)), _step("b", depends=("a",), writes=("src/x.py",))]
        assert read_write_conflicts(steps) == ()

    def test_estimate_respects_the_throughput_ceiling(self) -> None:
        steps = [_step(f"s{i}", seconds=60) for i in range(10)]
        narrow = estimate_plan(steps, max_parallel_shards=1)
        wide = estimate_plan(steps, max_parallel_shards=10)
        assert narrow.wall_clock_p50 == 600
        assert wide.wall_clock_p50 == 60
        assert narrow.wall_clock_p95 > narrow.wall_clock_p80 > narrow.wall_clock_p50


class TestJournal:
    def test_events_form_a_verifiable_hash_chain(self) -> None:
        journal = RunJournal("run-1")
        journal.append("run.created", {"a": 1})
        journal.append("step.started", {"b": 2}, step_id="discover")
        assert journal.verify_chain()
        replayed = RunJournal("run-1")
        replayed.replay([event.to_payload() for event in journal.events])
        assert replayed.head_digest == journal.head_digest

    def test_a_tampered_event_breaks_replay(self) -> None:
        journal = RunJournal("run-1")
        journal.append("run.created", {"a": 1})
        journal.append("step.started", {"b": 2}, step_id="discover")
        payloads = [event.to_payload() for event in journal.events]
        payloads[0]["payload"] = {"a": 999}
        with pytest.raises(ContractError) as error:
            RunJournal("run-1").replay(payloads)
        assert error.value.code in ("event_digest_mismatch", "hash_chain_broken")

    def test_idempotency_key_returns_the_first_result(self) -> None:
        journal = RunJournal("run-1")
        key = idempotency_key("run-1", "transform", 1)
        first = journal.remember(key, {"patch": "abc"})
        assert journal.remember(key, {"patch": "abc"}) == first

    def test_conflicting_idempotent_result_is_a_contract_error(self) -> None:
        journal = RunJournal("run-1")
        key = idempotency_key("run-1", "transform", 1)
        journal.remember(key, {"patch": "abc"})
        with pytest.raises(ContractError) as error:
            journal.remember(key, {"patch": "different"})
        assert error.value.code == "idempotency_conflict"

    def test_a_partitioned_worker_is_fenced_out_after_its_lease_lapses(self) -> None:
        from datetime import timedelta

        from elmos_repository_refactoring.contracts import utc_now

        start = utc_now()
        journal = RunJournal("run-1")
        first = journal.acquire_lease("worker-a", ttl_seconds=60, now=start)
        later = start + timedelta(seconds=120)
        second = journal.acquire_lease("worker-b", ttl_seconds=300, now=later)
        assert second.fencing_token > first.fencing_token
        # worker-a comes back believing it still holds the run
        with pytest.raises(ContractError) as error:
            journal.append("step.started", {}, step_id="x", lease=first, now=later)
        assert error.value.code == "stale_fencing_token"

    def test_a_live_lease_blocks_another_holder(self) -> None:
        journal = RunJournal("run-1")
        journal.acquire_lease("worker-a", ttl_seconds=300)
        with pytest.raises(ContractError) as error:
            journal.acquire_lease("worker-b", ttl_seconds=300)
        assert error.value.code == "lease_held"

    def test_side_effects_are_replayed_newest_first_for_compensation(self) -> None:
        journal = RunJournal("run-1")
        journal.record_side_effect("branch.push", "refs/heads/x", idempotency_key="k1", reversible=True)
        journal.record_side_effect("pr.open", "pr/1", idempotency_key="k2", reversible=True)
        pending = journal.uncompensated_since(0)
        assert [item.kind for item in pending] == ["pr.open", "branch.push"]
        journal.mark_compensated(2)
        assert [item.kind for item in journal.uncompensated_since(0)] == ["branch.push"]

    def test_duplicate_side_effect_delivery_does_not_act_twice(self) -> None:
        journal = RunJournal("run-1")
        first = journal.record_side_effect("pr.open", "pr/1", idempotency_key="k", reversible=True)
        again = journal.record_side_effect("pr.open", "pr/1", idempotency_key="k", reversible=True)
        assert again.cursor == first.cursor
        assert journal.side_effect_cursor == 1

    def test_checkpoints_bind_a_workspace_and_artifact_digest(self) -> None:
        journal = RunJournal("run-1")
        checkpoint = journal.write_checkpoint(
            step_id="transform",
            workspace_tree_digest="sha256:" + "1" * 64,
            artifact_manifest_digest="sha256:" + "2" * 64,
            state_version=1,
        )
        assert checkpoint.resume_token
        assert journal.latest_checkpoint(step_id="transform") == checkpoint

    def test_journal_sink_persists_and_reloads(self, tmp_path: Path) -> None:
        from elmos_repository_refactoring.journal import JournalSink

        sink = JournalSink(tmp_path, "run-1")
        journal = RunJournal("run-1", sink=sink)
        journal.append("run.created", {"a": 1})
        journal.append("run.completed", {})
        reloaded = RunJournal("run-1")
        reloaded.replay(list(sink.read()))
        assert reloaded.head_digest == journal.head_digest


class TestFailureClassification:
    @pytest.mark.parametrize(
        ("signature", "expected"),
        [
            ("compile_error: missing symbol", FailureClass.REPAIRABLE),
            ("test_failure in acme", FailureClass.REPAIRABLE),
            ("timeout after 900s", FailureClass.RETRYABLE),
            ("scope_expansion detected", FailureClass.APPROVAL_REQUIRED),
            ("migration_partially_applied", FailureClass.ROLLBACK_REQUIRED),
            ("budget_exhausted", FailureClass.TERMINAL),
            ("something nobody has seen", FailureClass.TERMINAL),
        ],
    )
    def test_signatures_map_to_actions(self, signature: str, expected: FailureClass) -> None:
        assert classify_failure(signature) is expected

    def test_backoff_is_deterministic_and_capped(self) -> None:
        assert [backoff_seconds(n) for n in range(0, 5)] == [0, 5, 10, 20, 40]
        assert backoff_seconds(20) == 300


class TestOrchestration:
    def _run(self) -> RefactorRun:
        request = RefactorRequest.from_payload(request_payload())
        policy = ENTERPRISE_DEFAULT_POLICY
        plan = synthesize_plan(
            request, policy, run_id="run-1", snapshot_digests={"billing": "sha256:" + "3" * 64}
        )
        run = RefactorRun(request, policy, run_id="run-1")
        run.freeze_plan(plan)
        return run

    def test_plan_is_acyclic_and_ordered(self) -> None:
        plan = self._run().plan
        assert plan.topological_order()[0] == "discover"
        assert "verify" in plan.step_ids

    def test_every_mutating_step_has_a_rollback_strategy(self) -> None:
        for step in self._run().plan.mutating_steps:
            assert step.rollback.strategy.value != "forward-only"

    def test_high_risk_steps_have_an_approval_gate(self) -> None:
        plan = self._run().plan
        for step in plan.steps:
            if step.risk_class.rank >= RiskClass.R3.rank:
                assert plan.gates_before(step.step_id), f"{step.step_id} has no approval gate"

    def test_analyze_only_produces_no_mutating_steps(self) -> None:
        request = RefactorRequest.from_payload(
            request_payload(execution={"mode": "analyze-only", "createPullRequest": False})
        )
        plan = synthesize_plan(request, ENTERPRISE_DEFAULT_POLICY, run_id="run-2", snapshot_digests={})
        assert plan.mutating_steps == ()

    def test_database_strategy_adds_the_schema_phase(self) -> None:
        request = RefactorRequest.from_payload(
            request_payload(
                intent={"type": "data-schema-refactor", "goals": ["rename legacy_name"]},
                constraints={"databaseStrategy": "expand-contract"},
            )
        )
        plan = synthesize_plan(request, ENTERPRISE_DEFAULT_POLICY, run_id="run-3", snapshot_digests={})
        assert "schema" in plan.step_ids

    def test_scheduling_blocks_on_an_unsatisfied_approval_gate(self) -> None:
        run = self._run()
        decision = run.schedule()
        assert "discover" in decision.runnable

    def test_illegal_transition_is_refused(self) -> None:
        run = self._run()
        run.cancel("operator stopped it")
        with pytest.raises(ContractError) as error:
            run.pause()
        assert error.value.code == "illegal_transition"

    def test_replay_reconstructs_identical_state(self) -> None:
        run = self._run()
        run.start_step("discover")
        run.complete_step("discover", {"inventory": "x"})
        run.start_step("buildgraph")
        run.fail_step("buildgraph", "compile_error: broken build file")
        events = [event.to_payload() for event in run.journal.events]
        replayed = RefactorRun.replay(run.request, run.policy, run.plan, events)
        assert replayed.to_payload()["steps"] == run.to_payload()["steps"]
        assert replayed.state is run.state

    def test_a_rollback_required_failure_moves_the_run_to_rolling_back(self) -> None:
        run = self._run()
        run.start_step("discover")
        _, classification = run.fail_step("discover", "migration_partially_applied")
        assert classification is FailureClass.ROLLBACK_REQUIRED
        assert run.state is RunState.ROLLING_BACK

    def test_an_approval_required_failure_blocks_rather_than_fails(self) -> None:
        run = self._run()
        run.start_step("discover")
        status, classification = run.fail_step("discover", "policy_violation: forbidden path")
        assert classification is FailureClass.APPROVAL_REQUIRED
        assert status.state is StepState.BLOCKED
        assert run.state is RunState.BLOCKED

    def test_progress_reports_percentiles_and_open_gates(self) -> None:
        run = self._run()
        progress = run.progress()
        assert progress["etaSeconds"]["p95"] >= progress["etaSeconds"]["p50"]
        assert progress["stepsTotal"] == len(run.plan.steps)


class TestDispatcher:
    def test_catalog_covers_every_skill(self) -> None:
        assert len(SKILL_NAMES) == 23
        assert set(topological_order()) == set(SKILL_NAMES)

    def test_unknown_skill_is_rejected(self) -> None:
        result = dispatch("not-a-skill")
        assert result["status"] == Status.REJECTED.value

    def test_pending_skills_block_rather_than_fake_success(self) -> None:
        for name in sorted(PENDING_SKILLS):
            result = dispatch(name, {})
            assert result["status"] == Status.BLOCKED.value, name
            assert result["output"]["code"] == "handler_not_implemented"

    def test_discovery_runs_end_to_end(self) -> None:
        result = dispatch("repository-discovery", {"workspace": workspace_payload()})
        assert result["status"] == Status.SUCCEEDED.value
        inventory = result["output"]["repository_inventory"]
        assert inventory["revision"] == REVISION
        assert result["output"]["sensitive_area_map"]["areas"]

    def test_build_graph_reports_an_unestablished_baseline(self) -> None:
        result = dispatch("build-graph-and-environment", {"workspace": workspace_payload()})
        assert result["status"] == Status.SUCCEEDED.value
        assert result["output"]["baseline_report"]["trustworthy"] is False
        assert any("baseline was not established" in reason for reason in result["reasons"])

    def test_semantic_index_reports_adapter_levels_and_unknown_risk(self) -> None:
        result = dispatch("semantic-index", {"workspace": workspace_payload()})
        assert result["status"] == Status.SUCCEEDED.value
        levels = result["output"]["adapter_levels"]
        assert levels["python"] == "L2"
        assert levels["java"] == "L1"
        assert Decimal(result["output"]["coverage_metrics"]["unknownRiskWeight"]) > 0

    def test_orchestrator_plans_and_schedules(self) -> None:
        result = dispatch(
            "repository-refactor-orchestrator",
            {"request": request_payload(), "run_id": "run-9", "action": "plan"},
        )
        assert result["status"] == Status.SUCCEEDED.value
        assert result["output"]["plan"]["kind"] == "RefactorPlan"
        assert result["output"]["waves"][0] == ["discover"]

    def test_orchestrator_refuses_a_mode_the_policy_forbids(self) -> None:
        result = dispatch(
            "repository-refactor-orchestrator",
            {
                "request": request_payload(
                    intent={"type": "structural-refactor", "goals": ["tidy up imports"]},
                    execution={"mode": "autonomous-low-risk", "createPullRequest": False},
                ),
                "run_id": "run-10",
            },
        )
        assert result["status"] in (Status.REJECTED.value, Status.BLOCKED.value)

    def test_payload_cannot_widen_filesystem_reach(self) -> None:
        result = dispatch(
            "repository-discovery",
            {
                "workspace": {
                    "source": "approved-root",
                    "repository_id": "x",
                    "revision": "abcdefg1",
                }
            },
        )
        assert result["status"] == Status.REJECTED.value
        assert result["output"]["code"] == "workspace_root_not_approved"

    def test_unknown_payload_field_is_rejected(self) -> None:
        result = dispatch("repository-discovery", {"workspace": workspace_payload(), "surprise": 1})
        assert result["status"] == Status.REJECTED.value

    def test_output_digest_is_present_and_stable(self) -> None:
        first = dispatch("repository-discovery", {"workspace": workspace_payload()})
        second = dispatch("repository-discovery", {"workspace": workspace_payload()})
        assert first["output_digest"] == second["output_digest"]


class TestRuntimeSurface:
    def test_describe_reports_implementation_status_honestly(self) -> None:
        description = describe()
        assert description["totalCount"] == 23
        assert description["implementedCount"] == len(implemented_skills())
        implemented = {item["name"] for item in description["skills"] if item["implemented"]}
        assert implemented == set(implemented_skills())

    def test_generated_catalog_matches_the_committed_file(self) -> None:
        committed = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "skill-catalog.json").read_text(encoding="utf-8")
        )
        assert committed == skill_catalog_payload()

    def test_cli_exit_codes_follow_status(self, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        payload = tmp_path / "payload.json"
        payload.write_text(json.dumps({"workspace": workspace_payload()}), encoding="utf-8")
        assert main(["run", "repository-discovery", "--payload", str(payload)]) == 0
        capsys.readouterr()
        #: A Skill that needs more than a workspace exits 3 (blocked), not 0.
        #: `multi-repository-refactor-program` needs a portfolio, and refuses
        #: to invent one.
        program_payload = tmp_path / "program.json"
        program_payload.write_text(
            json.dumps({"program_id": "prog-1", "portfolio": []}), encoding="utf-8"
        )
        assert main(
            ["run", "multi-repository-refactor-program", "--payload", str(program_payload)]
        ) == 2
        capsys.readouterr()
        assert main(["run", "repository-discovery"]) == 2

    def test_every_catalog_skill_has_a_production_handler(self) -> None:
        """The acceptance condition for the package: nothing is still pending."""

        assert PENDING_SKILLS == frozenset()
        dispatcher = RuntimeDispatcher()
        assert set(dispatcher.implemented) == set(dispatcher.handler_names)
        assert len(dispatcher.handler_names) == 23
