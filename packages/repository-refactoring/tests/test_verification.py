"""Verification, anti-cheat, API compatibility, repair, approval, rollout,
recovery and evidence."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from elmos_repository_refactoring import anticheat, apicompat
from elmos_repository_refactoring.anticheat import analyse as analyse_cheating
from elmos_repository_refactoring.approval import (
    ApprovalRecord,
    BoundDigests,
    build_context,
    evaluate_approvals,
    request_approval,
)
from elmos_repository_refactoring.buildgraph import BaselineReport, baseline_requests, build_graph
from elmos_repository_refactoring.contracts import (
    CompatibilityImpact,
    ContractError,
    GateOutcome,
    RiskClass,
    Status,
    isoformat_utc,
    utc_now,
)
from elmos_repository_refactoring.discovery import discover
from elmos_repository_refactoring.dispatcher import PENDING_SKILLS, dispatch
from elmos_repository_refactoring.evidence import (
    BundleInputs,
    GateDecisionRecord,
    artifact_from_payload,
    assemble,
    sign,
    verify_bundle,
)
from elmos_repository_refactoring.index import build_index
from elmos_repository_refactoring.journal import RunJournal
from elmos_repository_refactoring.patch import TextEdit, patch_from_edits
from elmos_repository_refactoring.recovery import (
    RecoveryAction,
    last_consistent_checkpoint,
    plan_rollback,
)
from elmos_repository_refactoring.repair import (
    RepairBudgetState,
    generate_candidate,
    normalise_failures,
    repair,
)
from elmos_repository_refactoring.rollout import (
    DEFAULT_STAGES,
    GuardrailReading,
    RolloutDecision,
    evaluate_stage,
    plan_rollout,
    run_ladder,
    split_changesets,
)
from elmos_repository_refactoring.sandbox import ExecutionResult, ExecutionStatus
from elmos_repository_refactoring.verification import (
    EXECUTED_GATES,
    compare_to_baseline,
    plan_executions,
)
from elmos_repository_refactoring.workspace import WorkspaceSnapshot

from .fixtures import request_payload, workspace_payload

RENAME_REQUEST = request_payload(
    intent={
        "type": "structural-refactor",
        "goals": ["rename `post_entry` to `record_entry` across the billing package"],
        "nonGoals": [],
    },
    constraints={"publicApiCompatibility": "approved-break"},
)


def _snapshot() -> WorkspaceSnapshot:
    return WorkspaceSnapshot.from_payload(workspace_payload())


def _snapshot_of(files: dict[str, str]) -> WorkspaceSnapshot:
    """A minimal snapshot from a path -> text mapping."""

    return WorkspaceSnapshot.from_payload(
        {
            "source": "inline",
            "repository_id": "r",
            "revision": "a" * 40,
            "files": [{"path": key, "content": value} for key, value in sorted(files.items())],
        }
    )


def _recorded_successes() -> list[dict[str, object]]:
    """Recordings for every command verification and baseline would issue."""

    snapshot = _snapshot()
    inventory = discover(snapshot)
    graph = build_graph(snapshot, inventory)
    languages = [item.language for item in inventory.languages if item.language != "unknown"][:6]
    requests = [*plan_executions(list(EXECUTED_GATES), languages), *baseline_requests(graph)]
    unique: dict[str, str] = {}
    for request in requests:
        unique.setdefault(request.digest, request.request_id)
    return [
        {
            "requestId": request_id,
            "requestDigest": digest,
            "status": "completed",
            "exitCode": 0,
            "durationMs": 10,
        }
        for digest, request_id in unique.items()
    ]


class TestAntiCheat:
    def test_added_skip_marker_is_detected(self) -> None:
        snapshot = _snapshot()
        edit = TextEdit(
            path="tests/test_billing.py",
            start_line=1,
            start_column=0,
            end_line=1,
            end_column=0,
            replacement="import pytest\n\n@pytest.mark.skip\n",
        )
        patch, updated = patch_from_edits(snapshot, [edit])
        report = analyse_cheating(patch, snapshot, updated, test_paths=("tests/test_billing.py",))
        assert not report.clean
        assert any(item.code == "anti-cheat/skip-marker" for item in report.findings)

    def test_deleting_a_test_file_is_detected(self) -> None:
        snapshot = _snapshot()
        patch, updated = patch_from_edits(snapshot, [], deletions=["tests/test_billing.py"])
        report = analyse_cheating(patch, snapshot, updated, test_paths=("tests/test_billing.py",))
        assert report.test_files_deleted == ("tests/test_billing.py",)
        assert not report.clean

    def test_removing_a_test_function_is_detected(self) -> None:
        snapshot = _snapshot()
        stripped = "from acme.billing import BillingService\n\n\ndef helper() -> None:\n    pass\n"
        updated = snapshot.with_files({"tests/test_billing.py": stripped})
        from elmos_repository_refactoring.patch import diff_snapshots

        patch = diff_snapshots(snapshot, updated)
        report = analyse_cheating(patch, snapshot, updated, test_paths=("tests/test_billing.py",))
        assert any("test_charge_returns_entry" in item for item in report.tests_removed)

    def test_blanket_noqa_is_detected(self) -> None:
        snapshot = _snapshot()
        edit = TextEdit(
            path="src/acme/ledger.py",
            start_line=1,
            start_column=0,
            end_line=1,
            end_column=0,
            replacement="# noqa\n",
        )
        patch, updated = patch_from_edits(snapshot, [edit])
        report = analyse_cheating(patch, snapshot, updated)
        assert any(item.code == "anti-cheat/suppression" for item in report.findings)

    def test_a_clean_rename_trips_nothing(self) -> None:
        snapshot = _snapshot()
        patch, updated = patch_from_edits(
            snapshot, [TextEdit(path="src/acme/ledger.py", start_line=5, start_column=4,
                                end_line=5, end_column=14, replacement="record_entry")]
        )
        assert analyse_cheating(patch, snapshot, updated).clean


class TestApiCompatibility:
    def test_removing_a_public_symbol_is_a_break(self) -> None:
        before = apicompat.ApiSurface(
            members=(
                apicompat.ApiMember(identity="m.f", kind="function", language="python", path="m.py",
                                    signature="(a)"),
            )
        )
        after = apicompat.ApiSurface(members=())
        diff = apicompat.diff_surfaces(before, after)
        assert diff.breaks
        assert diff.changes[0].impact in (CompatibilityImpact.SOURCE_BREAK, CompatibilityImpact.BINARY_BREAK)

    def test_adding_a_required_parameter_is_a_source_break(self) -> None:
        before = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="(a)"),)
        )
        after = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="(a, b)"),)
        )
        diff = apicompat.diff_surfaces(before, after)
        assert diff.source_breaks == 1
        assert "not an additive change" in diff.changes[0].detail

    def test_adding_an_optional_parameter_is_not_a_break(self) -> None:
        before = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="(a)"),)
        )
        after = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="(a, b=1)"),)
        )
        assert apicompat.diff_surfaces(before, after).source_breaks == 0

    def test_changing_a_wire_number_is_a_wire_break(self) -> None:
        before = apicompat.ApiSurface(
            members=(apicompat.ApiMember("p#M.f", "wire-field", "protobuf", "p.proto", wire_number=1),)
        )
        after = apicompat.ApiSurface(
            members=(apicompat.ApiMember("p#M.f", "wire-field", "protobuf", "p.proto", wire_number=2),)
        )
        diff = apicompat.diff_surfaces(before, after)
        assert diff.wire_breaks == 1
        assert "the wire carries the number" in diff.changes[0].detail

    def test_wire_surface_is_extracted_from_proto(self) -> None:
        surface = apicompat.extract_wire_surface(
            {
                "a.proto": (
                    "message Charge {\n  string id = 1;\n  int32 amount = 2;\n}\n"
                    "enum Kind {\n  UNKNOWN = 0;\n  CARD = 1;\n}\n"
                )
            }
        )
        numbers = {item.identity: item.wire_number for item in surface.members}
        assert numbers["a.proto#Charge.id"] == 1
        #: The enum member is scoped by its enum, not filed under a shared
        #: "enum" bucket: two enums in one file may both have a CARD member.
        assert numbers["a.proto#Kind.CARD"] == 1

    def test_two_enums_in_one_file_do_not_collide(self) -> None:
        surface = apicompat.extract_wire_surface(
            {
                "a.proto": (
                    "enum Kind {\n  UNSET = 0;\n  CARD = 1;\n}\n"
                    "enum Method {\n  UNSET = 0;\n  CARD = 7;\n}\n"
                )
            }
        )
        numbers = {item.identity: item.wire_number for item in surface.members}
        assert numbers["a.proto#Kind.CARD"] == 1
        assert numbers["a.proto#Method.CARD"] == 7

    def test_field_renamed_at_a_stable_number_is_not_a_wire_break(self) -> None:
        """protobuf keys the binary encoding on the number, not the name."""

        before = apicompat.extract_wire_surface(
            {"a.proto": "message Charge {\n  string currency = 2;\n}\n"}
        )
        after = apicompat.extract_wire_surface(
            {"a.proto": "message Charge {\n  string currency_code = 2;\n}\n"}
        )
        diff = apicompat.diff_surfaces(before, after)
        assert diff.wire_breaks == 0
        assert len(diff.changes) == 1
        change = diff.changes[0]
        assert change.change == "wire-member-renamed"
        assert change.impact is CompatibilityImpact.SOURCE_BREAK
        assert change.after == "a.proto#Charge.currency_code"

    def test_field_renumbered_is_still_a_wire_break(self) -> None:
        before = apicompat.extract_wire_surface(
            {"a.proto": "message Charge {\n  string currency = 2;\n}\n"}
        )
        after = apicompat.extract_wire_surface(
            {"a.proto": "message Charge {\n  string currency = 4;\n}\n"}
        )
        assert apicompat.diff_surfaces(before, after).wire_breaks == 1

    def test_sync_to_async_is_a_source_break(self) -> None:
        before = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="(a)",
                                         attributes={"async": False}),)
        )
        after = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="(a)",
                                         attributes={"async": True}),)
        )
        diff = apicompat.diff_surfaces(before, after)
        assert any(item.change == "sync-async-changed" for item in diff.changes)

    def test_strict_policy_forbids_additions_too(self) -> None:
        before = apicompat.ApiSurface(members=())
        after = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.g", "function", "python", "m.py", signature="()"),)
        )
        diff = apicompat.diff_surfaces(before, after)
        decision = apicompat.decide(diff, public_api_policy="strict")
        assert not decision.allowed
        backward = apicompat.decide(diff, public_api_policy="backward-compatible")
        assert backward.allowed

    def test_deprecation_plan_orders_expand_before_contract(self) -> None:
        before = apicompat.ApiSurface(
            members=(apicompat.ApiMember("m.f", "function", "python", "m.py", signature="()"),)
        )
        diff = apicompat.diff_surfaces(before, apicompat.ApiSurface(members=()))
        phases = [item.phase for item in apicompat.deprecation_plan(diff)]
        assert phases.index("expand") < phases.index("observe") < phases.index("contract")


class TestVerification:
    def test_no_executor_means_undecided_not_passed(self) -> None:
        result = dispatch(
            "test-and-verification", {"request": RENAME_REQUEST, "workspace": workspace_payload()}
        )
        assert result["status"] == Status.BLOCKED.value
        gates = {item["gate"]: item["decision"] for item in result["output"]["gate_decisions"]}
        assert gates["build"] == "fail"
        assert any("evidence was not produced" in item for item in result["reasons"])

    def test_recorded_evidence_turns_mechanical_gates_green(self) -> None:
        result = dispatch(
            "test-and-verification",
            {"request": RENAME_REQUEST, "workspace": workspace_payload()},
            trusted_context={"recorded_executions": _recorded_successes()},
        )
        gates = {item["gate"]: item["decision"] for item in result["output"]["gate_decisions"]}
        for gate in ("parse", "round-trip", "idempotence", "scope-containment", "anti-cheat",
                     "typecheck", "build", "changed-target-tests", "rollback-proof",
                     "api-compatibility", "evidence-completeness"):
            assert gates[gate] == "pass", f"{gate} is {gates[gate]}"

    def test_rollback_proof_is_computed_by_inverting_the_patch(self) -> None:
        result = dispatch(
            "test-and-verification",
            {"request": RENAME_REQUEST, "workspace": workspace_payload()},
            trusted_context={"recorded_executions": _recorded_successes()},
        )
        proof = next(
            item for item in result["output"]["gate_decisions"] if item["gate"] == "rollback-proof"
        )
        assert proof["decision"] == "pass"
        assert "restores the exact base tree digest" in proof["detail"]

    def test_an_untrustworthy_baseline_attributes_every_failure_to_the_change(self) -> None:
        baseline = BaselineReport(status=ExecutionStatus.NOT_RUN, build_ok=None, test_ok=None)
        failing = ExecutionResult(
            request_id="t", request_digest="d", status=ExecutionStatus.FAILED, exit_code=1,
            stdout="tests/test_a.py::test_one FAILED", executor="recorded",
        )
        diff = compare_to_baseline(baseline, [failing])
        assert diff.baseline_trustworthy is False
        assert diff.new_failures
        assert diff.pre_existing_failures == ()

    def test_a_trustworthy_baseline_subtracts_pre_existing_failures(self) -> None:
        baseline = BaselineReport(
            status=ExecutionStatus.FAILED,
            build_ok=False,
            test_ok=False,
            pre_existing_failures=("tests/test_a.py::test_one",),
        )
        failing = ExecutionResult(
            request_id="t", request_digest="d", status=ExecutionStatus.FAILED, exit_code=1,
            stdout="tests/test_a.py::test_one\ntests/test_b.py::test_two", executor="recorded",
        )
        diff = compare_to_baseline(baseline, [failing])
        assert diff.pre_existing_failures == ("tests/test_a.py::test_one",)
        assert diff.new_failures == ("tests/test_b.py::test_two",)

    def test_flaky_tests_are_quarantined_not_passed(self) -> None:
        baseline = BaselineReport(status=ExecutionStatus.COMPLETED, build_ok=True, test_ok=True)
        first = ExecutionResult(
            request_id="t", request_digest="d", status=ExecutionStatus.FAILED, exit_code=1,
            stdout="tests/test_a.py::test_flaky", executor="recorded",
        )
        rerun = ExecutionResult(
            request_id="t", request_digest="d", status=ExecutionStatus.COMPLETED, exit_code=0,
            executor="recorded",
        )
        diff = compare_to_baseline(baseline, [first], reruns=[rerun])
        assert diff.flaky == ("tests/test_a.py::test_flaky",)


class TestRepair:
    def test_failure_normalisation_deduplicates_by_identity(self) -> None:
        text = (
            "a.py:1:1: F401 `os` imported but unused\n"
            "a.py:1:1: F401 `os` imported but unused\n"
            "NameError: name 'Thing' is not defined\n"
        )
        signatures = normalise_failures(text)
        kinds = {item.kind for item in signatures}
        assert kinds == {"unused-import", "unresolved-name"}
        assert len(signatures) == 2

    def test_syntax_errors_are_never_auto_repaired(self) -> None:
        signature = normalise_failures("SyntaxError: invalid syntax")[0]
        candidate = generate_candidate(signature, _snapshot(), _index())
        assert not candidate.actionable
        assert "would hide it" in candidate.rationale

    def test_an_ambiguous_import_is_refused(self) -> None:
        signature = normalise_failures("NameError: name 'Nowhere' is not defined")[0]
        candidate = generate_candidate(signature, _snapshot(), _index(), failing_path="src/acme/billing.py")
        assert not candidate.actionable
        assert "ambiguous" in candidate.rationale or "no single module" in candidate.rationale

    def test_repeating_a_signature_stops_the_loop(self) -> None:
        signature = normalise_failures("src/acme/billing.py:3:1: F401 `os` imported but unused")[0]
        outcome = repair(
            [signature, signature],
            _snapshot(),
            _index(),
            budget=RepairBudgetState(max_attempts=5, max_changed_files=10, max_cost_usd=Decimal("0")),
        )
        assert "reappeared after a repair" in outcome.stopped_because

    def test_budget_exhaustion_stops_repair(self) -> None:
        signatures = normalise_failures(
            "src/acme/billing.py:3:1: F401 `os` imported but unused\n"
            "src/acme/ledger.py:2:1: F401 `Decimal` imported but unused\n"
        )
        outcome = repair(
            signatures,
            _snapshot(),
            _index(),
            budget=RepairBudgetState(max_attempts=1, max_changed_files=10, max_cost_usd=Decimal("0")),
        )
        assert "budget exhausted" in outcome.stopped_because

    def test_repair_cannot_produce_a_cheat(self) -> None:
        """The anti-cheat gate is applied to every candidate, not only to the plan."""

        signature = normalise_failures("src/acme/billing.py:3:1: F401 `os` imported but unused")[0]
        outcome = repair(
            [signature],
            _snapshot(),
            _index(),
            budget=RepairBudgetState(max_attempts=3, max_changed_files=10, max_cost_usd=Decimal("0")),
            test_paths=("tests/test_billing.py",),
        )
        for attempt in outcome.attempts:
            assert "anti-cheat" not in attempt.reason or not attempt.accepted


def _index():  # type: ignore[no-untyped-def]
    snapshot = _snapshot()
    inventory = discover(snapshot)
    return build_index(snapshot, inventory, build_graph(snapshot, inventory))


class TestApproval:
    def _bound(self) -> BoundDigests:
        return BoundDigests(
            request="sha256:" + "1" * 64,
            plan="sha256:" + "2" * 64,
            recipe_lock="sha256:" + "3" * 64,
            patch="sha256:" + "4" * 64,
        )

    def _request(self, **overrides):  # type: ignore[no-untyped-def]
        context = build_context(
            run_id="r1",
            gate_id="g1",
            goals=("do the thing",),
            risk_class=RiskClass.R3,
            risk_reasons=("it is risky",),
            patch_summary={"changedFiles": 2, "changedLines": 10},
            diff_excerpt="--- a\n+++ b\n",
            validation_summary={},
            rollback_summary={},
        )
        defaults = {
            "run_id": "r1",
            "gate_id": "g1",
            "roles": ("tech-lead",),
            "minimum_approvers": 1,
            "bound": self._bound(),
            "context": context,
        }
        defaults.update(overrides)
        return request_approval(**defaults)  # type: ignore[arg-type]

    def _record(self, **overrides):  # type: ignore[no-untyped-def]
        payload = {
            "approvalId": "a1",
            "runId": "r1",
            "gateId": "g1",
            "decision": "approve",
            "actor": {"subject": "alice", "roles": ["tech-lead"]},
            "boundDigests": self._bound().to_payload(),
            "decidedAt": isoformat_utc(utc_now()),
        }
        payload.update(overrides)
        return ApprovalRecord.from_payload(payload)

    def test_an_approval_satisfies_its_gate(self) -> None:
        verdict = evaluate_approvals(self._request(), [self._record()], current=self._bound())
        assert verdict.satisfied

    def test_a_changed_patch_invalidates_the_approval(self) -> None:
        drifted = BoundDigests(
            request=self._bound().request,
            plan=self._bound().plan,
            recipe_lock=self._bound().recipe_lock,
            patch="sha256:" + "9" * 64,
        )
        verdict = evaluate_approvals(self._request(), [self._record()], current=drifted)
        assert not verdict.satisfied
        assert "never generalises" in verdict.reasons[0]

    def test_an_expired_window_is_a_refusal(self) -> None:
        request = self._request(ttl_seconds=60)
        later = utc_now() + timedelta(seconds=120)
        verdict = evaluate_approvals(request, [self._record()], current=self._bound(), now=later)
        assert not verdict.satisfied
        assert any("timeout is a refusal" in item for item in verdict.reasons)

    def test_self_approval_is_refused(self) -> None:
        request = self._request(requested_by="alice")
        verdict = evaluate_approvals(request, [self._record()], current=self._bound())
        assert not verdict.satisfied

    def test_four_eyes_needs_two_distinct_subjects(self) -> None:
        request = self._request(minimum_approvers=2)
        same_person = [self._record(), self._record(approvalId="a2")]
        assert not evaluate_approvals(request, same_person, current=self._bound()).satisfied
        two_people = [
            self._record(),
            self._record(approvalId="a2", actor={"subject": "bob", "roles": ["tech-lead"]}),
        ]
        assert evaluate_approvals(request, two_people, current=self._bound()).satisfied

    def test_a_rejection_short_circuits(self) -> None:
        verdict = evaluate_approvals(
            self._request(),
            [self._record(decision="reject", reason="not now")],
            current=self._bound(),
        )
        assert not verdict.satisfied
        assert "rejected by alice" in verdict.reasons[0]

    def test_conditions_must_be_satisfiable_and_true(self) -> None:
        record = self._record(
            decision="approve-with-conditions",
            conditions=[{"id": "c1", "predicate": "rollout.canary_passed"}],
        )
        unmet = evaluate_approvals(self._request(), [record], current=self._bound(), condition_context={})
        assert not unmet.satisfied
        assert unmet.unmet_conditions
        met = evaluate_approvals(
            self._request(),
            [record],
            current=self._bound(),
            condition_context={"rollout": {"canary_passed": True}},
        )
        assert met.satisfied

    def test_approve_with_conditions_requires_conditions(self) -> None:
        with pytest.raises(ContractError) as error:
            self._record(decision="approve-with-conditions")
        assert error.value.code == "conditions_required"

    def test_wrong_role_is_not_counted(self) -> None:
        verdict = evaluate_approvals(
            self._request(roles=("security-owner",)),
            [self._record()],
            current=self._bound(),
        )
        assert not verdict.satisfied


class TestRollout:
    def test_no_verified_rollback_blocks_the_canary(self) -> None:
        plan = plan_rollout(risk_class=RiskClass.R3, rollback_verified=False)
        assert not plan.startable
        assert "cannot be reversed" in plan.blocked_reason

    def test_r4_needs_a_business_signal_for_full_rollout(self) -> None:
        plan = plan_rollout(risk_class=RiskClass.R4, rollback_verified=True)
        assert not plan.startable
        assert "business" in plan.blocked_reason

    def test_a_missing_signal_holds_rather_than_advancing(self) -> None:
        plan = plan_rollout(risk_class=RiskClass.R3, rollback_verified=True)
        report = evaluate_stage(plan.stages[0], [])
        assert report.decision is RolloutDecision.HOLD
        assert "unavailable" in report.reasons[0]

    def test_a_breached_guardrail_rolls_back(self) -> None:
        plan = plan_rollout(risk_class=RiskClass.R3, rollback_verified=True)
        readings = [
            GuardrailReading("error-rate", Decimal("0.01"), Decimal("0.20"), Decimal("0.01")),
            GuardrailReading("latency-p95", Decimal("100"), Decimal("101"), Decimal("50")),
        ]
        assert evaluate_stage(plan.stages[0], readings).decision is RolloutDecision.ROLLBACK

    def test_the_ladder_stops_at_the_first_hold(self) -> None:
        plan = plan_rollout(risk_class=RiskClass.R3, rollback_verified=True)
        measurements = {
            plan.stages[0].stage_id: [
                GuardrailReading("error-rate", Decimal("0.01"), Decimal("0.01"), Decimal("0.05")),
                GuardrailReading("latency-p95", Decimal("100"), Decimal("101"), Decimal("50")),
            ]
        }
        reports = run_ladder(plan, measurements)
        assert reports[0].decision is RolloutDecision.ADVANCE
        assert reports[1].decision is RolloutDecision.HOLD
        assert len(reports) == 2

    def test_the_default_ladder_is_used_for_high_risk(self) -> None:
        plan = plan_rollout(risk_class=RiskClass.R3, rollback_verified=True)
        assert tuple(item.traffic_percent for item in plan.stages) == DEFAULT_STAGES

    def test_changesets_are_bounded_and_ordered(self) -> None:
        snapshot = _snapshot()
        inventory = discover(snapshot)
        graph = build_graph(snapshot, inventory)
        patch, _ = patch_from_edits(
            snapshot,
            [
                TextEdit(path="src/acme/ledger.py", start_line=5, start_column=4,
                         end_line=5, end_column=14, replacement="record_entry"),
                TextEdit(path="web/src/user-client.ts", start_line=5, start_column=0,
                         end_line=5, end_column=0, replacement="// touched\n"),
            ],
        )
        changesets = split_changesets(patch, graph, inventory)
        assert changesets
        assert all(len(item.paths) <= 40 for item in changesets)
        assert changesets[-1].depends_on or len(changesets) == 1


class TestRecovery:
    def _journal(self) -> RunJournal:
        journal = RunJournal("run-x")
        journal.append("run.created", {})
        journal.write_checkpoint(
            step_id="transform",
            workspace_tree_digest=_snapshot().tree_digest,
            artifact_manifest_digest="sha256:" + "0" * 64,
            state_version=1,
        )
        return journal

    def test_a_checkpoint_on_an_unreproducible_tree_is_not_a_recovery_point(self) -> None:
        journal = self._journal()
        assert last_consistent_checkpoint(journal, known_tree_digests=("sha256:" + "f" * 64,)) is None
        assert last_consistent_checkpoint(journal, known_tree_digests=(_snapshot().tree_digest,)) is not None

    def test_data_effects_with_unknown_reversibility_need_approval(self) -> None:
        journal = self._journal()
        journal.record_side_effect(
            "migration.apply", "public.users", idempotency_key="k1", reversible=True
        )
        plan = plan_rollback(journal, patch=None, checkpoint=journal.checkpoints[-1])
        holds = [item for item in plan.steps if item.action is RecoveryAction.HOLD_FOR_APPROVAL]
        assert holds
        assert "destroy the only copy" in holds[0].detail

    def test_data_rollback_stops_writes_and_switches_reads_first(self) -> None:
        journal = self._journal()
        journal.record_side_effect(
            "migration.apply", "public.users", idempotency_key="k1", reversible=True
        )
        plan = plan_rollback(
            journal, patch=None, checkpoint=journal.checkpoints[-1], data_reversibility_known=True
        )
        actions = [item.action for item in plan.steps]
        assert actions[0] in (RecoveryAction.STOP_WRITES, RecoveryAction.SWITCH_READS)

    def test_irreversible_effects_are_held_for_approval(self) -> None:
        journal = self._journal()
        journal.record_side_effect("email.send", "customer@example.com", idempotency_key="k2", reversible=False)
        plan = plan_rollback(journal, patch=None, checkpoint=journal.checkpoints[-1])
        assert any(item.approval_reason == "irreversible side effect" for item in plan.steps)

    def test_rollback_restores_the_original_tree(self) -> None:
        result = dispatch(
            "rollback-and-recovery", {"request": RENAME_REQUEST, "workspace": workspace_payload()}
        )
        assert result["status"] == Status.SUCCEEDED.value
        assert result["evidence"]["restoredTreeDigest"] == _snapshot().tree_digest

    def test_recovery_preserves_investigation_evidence(self) -> None:
        result = dispatch(
            "rollback-and-recovery", {"request": RENAME_REQUEST, "workspace": workspace_payload()}
        )
        incident = result["output"]["incidentReport"]
        assert any(item.startswith("journal:") for item in incident["preservedEvidence"])


class TestEvidence:
    def _bundle(self, **overrides):  # type: ignore[no-untyped-def]
        inputs = BundleInputs(
            request_digest="sha256:" + "1" * 64,
            plan_digest="sha256:" + "2" * 64,
            policy_digest="sha256:" + "3" * 64,
            recipe_lock_digest="sha256:" + "4" * 64,
            snapshot_digests={"repo": "sha256:" + "5" * 64},
        )
        defaults = {
            "run_id": "r1",
            "inputs": inputs,
            "artifacts": [artifact_from_payload("plan", "plan", {"a": 1})],
            "source_map": [{"hunkId": "h1", "path": "a.py", "actionIds": ["rename"], "symbols": ["m.f"]}],
            "gate_decisions": [
                GateDecisionRecord(gate="parse", decision=GateOutcome.PASS, evidence_refs=("e1",))
            ],
            "step_id": "transform",
            "recipe_execution_id": "lock1",
            "validation_refs": ["v1"],
        }
        defaults.update(overrides)
        return assemble(**defaults)  # type: ignore[arg-type]

    def test_a_complete_bundle_verifies(self) -> None:
        bundle = self._bundle()
        assert bundle.status == "complete"
        assert verify_bundle(bundle.to_payload()).valid

    def test_an_untraceable_hunk_makes_the_bundle_partial(self) -> None:
        bundle = self._bundle(source_map=[{"hunkId": "h1", "path": "a.py", "actionIds": []}])
        assert bundle.status == "partial"
        assert any("could not be traced" in item for item in bundle.incomplete_reasons)

    def test_a_waived_gate_without_an_approval_makes_the_bundle_partial(self) -> None:
        bundle = self._bundle(
            gate_decisions=[
                GateDecisionRecord(gate="full-tests", decision=GateOutcome.WAIVED, evidence_refs=())
            ]
        )
        assert bundle.status == "partial"

    def test_tampering_with_an_artifact_digest_fails_verification(self) -> None:
        payload = self._bundle().to_payload()
        payload["artifacts"][0]["digest"] = "sha256:" + "0" * 64
        outcome = verify_bundle(payload)
        assert not outcome.valid
        assert any("manifestDigest" in item for item in outcome.reasons)

    def test_signature_round_trips_and_detects_edits(self) -> None:
        signed = sign(self._bundle(), key_id="k", secret=b"secret")
        assert verify_bundle(signed.to_payload(), secret=b"secret").signature_checked
        tampered = signed.to_payload()
        tampered["runId"] = "r2"
        assert not verify_bundle(tampered, secret=b"secret").valid

    def test_a_signature_without_a_key_is_reported_not_assumed_valid(self) -> None:
        signed = sign(self._bundle(), key_id="k", secret=b"secret")
        outcome = verify_bundle(signed.to_payload())
        assert not outcome.valid
        assert "no key was supplied" in outcome.reasons[0]

    def test_end_to_end_bundle_is_produced_and_verified(self) -> None:
        result = dispatch(
            "evidence-and-audit",
            {"request": RENAME_REQUEST, "workspace": workspace_payload(), "signing_key": "s3cret"},
            trusted_context={"recorded_executions": _recorded_successes()},
        )
        manifest = result["output"]["signed_manifest"]
        assert manifest["signed"] is True
        assert manifest["verification"]["signatureChecked"] is True
        assert result["output"]["evidence_bundle"]["artifacts"]


class TestCoverageStatus:
    def test_pending_set_is_shrinking_and_explicit(self) -> None:
        assert "test-and-verification" not in PENDING_SKILLS
        assert "evidence-and-audit" not in PENDING_SKILLS
        for name in PENDING_SKILLS:
            assert dispatch(name, {})["status"] == Status.BLOCKED.value


class TestAssertionAccounting:
    """A rename rewrites the inside of an assertion; that is not a removal.

    Anti-cheat is only useful if it is quiet on legitimate work: a check that
    accuses every refactor of a test gets switched off, which is strictly
    worse than not having it.
    """

    BEFORE = {"tests/test_a.py": "def test_one():\n    assert f() == 1\n    assert g() == 2\n"}

    def _findings(self, after: dict[str, str]) -> tuple[int, int]:
        before_snapshot = _snapshot_of(self.BEFORE)
        after_snapshot = _snapshot_of(after)
        from elmos_repository_refactoring.patch import diff_snapshots

        report = anticheat.analyse(
            diff_snapshots(before_snapshot, after_snapshot),
            before_snapshot,
            after_snapshot,
            test_paths=("tests/test_a.py",),
        )
        located = [
            item for item in report.findings if item.code == "anti-cheat/assertions-removed"
        ]
        return len(located), report.assertions_removed

    def test_renaming_a_symbol_inside_an_assertion_is_not_a_removal(self) -> None:
        found, counted = self._findings(
            {"tests/test_a.py": "def test_one():\n    assert f2() == 1\n    assert g2() == 2\n"}
        )
        assert (found, counted) == (0, 0)

    def test_adding_an_assertion_is_not_a_removal(self) -> None:
        found, counted = self._findings(
            {
                "tests/test_a.py": (
                    "def test_one():\n    assert f() == 1\n    assert g() == 2\n    assert h() == 3\n"
                )
            }
        )
        assert (found, counted) == (0, 0)

    def test_deleting_one_assertion_is_reported_once(self) -> None:
        found, counted = self._findings({"tests/test_a.py": "def test_one():\n    assert f() == 1\n"})
        assert (found, counted) == (1, 1)

    def test_deleting_both_assertions_is_reported_twice(self) -> None:
        found, counted = self._findings({"tests/test_a.py": "def test_one():\n    pass\n"})
        assert (found, counted) == (2, 2)

    def test_two_removed_and_one_added_is_a_net_loss_of_one(self) -> None:
        """The net, not the gross: replacing two assertions with one still loses one."""

        found, counted = self._findings({"tests/test_a.py": "def test_one():\n    assert h() == 3\n"})
        assert (found, counted) == (1, 1)
