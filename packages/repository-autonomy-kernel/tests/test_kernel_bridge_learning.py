"""Bridge behaviour for the four learning-pack skills.

These four - agent-arena, repository-gym-golden-routes,
auto-improvement-inbox-and-skill-curator and demonstration-to-skill - are the
skills whose two implementations disagree most about what a result *means*, so
the routing between them is worth asserting rather than assuming.

Three properties are checked for each skill:

* a payload carrying the evidence the kernel needs reaches the kernel, and the
  answer contains something only the kernel can produce;
* a legacy-shaped payload still works, falls through with a recorded reason,
  and is not quietly answered by a kernel request assembled from invented data;
* the legacy answer says what it actually is.

The fourth property is the one that matters most and is checked last: a payload
the kernel *reads* and then rejects on a domain rule must surface that
rejection.  A fallback there would let the shallower engine overturn the
deeper one's correct refusal, which is strictly worse than not having the
kernel at all.

The full payloads are imported from each kernel module's own acceptance tests,
so "a realistic full payload" means the same payload that suite calls
realistic, not one written to fit the adapter.
"""

from __future__ import annotations

import pytest
from test_arena import request as arena_request
from test_curator import request as curator_request
from test_demo2skill import request as demonstration_request
from test_gym import request as gym_request

from elmos_repository_autonomy import kernel_bridge
from elmos_repository_autonomy.catalog import SKILL_SPECS
from elmos_repository_autonomy.dispatcher import AutonomyRuntime

ARENA = "agent-arena"
GYM = "repository-gym-golden-routes"
CURATOR = "auto-improvement-inbox-and-skill-curator"
DEMO = "demonstration-to-skill"


@pytest.fixture()
def runtime() -> AutonomyRuntime:
    return AutonomyRuntime()


# --- legacy-shaped payloads --------------------------------------------------
#
# These are the shapes the v2 dispatcher's own handlers were written against:
# flat lists of rows, a `quality` number per candidate, a `pass_score`.  The
# minimal ones are the payloads in test_kernel.py; they must keep working.

LEGACY_ARENA = {
    "arena_task_set": [{"id": "task-1", "quality": 0.6}],
    "agent_candidates": [{"id": "agent-a", "quality": 0.9, "cost": 12},
                         {"id": "agent-b", "quality": 0.4, "cost": 7}],
    "fixed_environments": {"image": "builder:2026"},
    "budgets": {"micros": 500_000},
    "evaluation_protocol": {"pass_score": 0.5},
}
LEGACY_GYM = {
    "benchmark_repositories": [{"id": "repo-alpha"}],
    "golden_task_specs": [{"id": "route-1"}],
    "fixed_images": {"image": "builder:2026"},
    "expected_contracts": {"gates": ["build"]},
    "chaos_scenarios": [{"id": "crash"}],
}
LEGACY_CURATOR = {"run_incidents": [{"code": "TOOL_DENIED", "severity": "P1"}]}
LEGACY_DEMO = {
    "validated_demonstration": {
        "status": "VALIDATED",
        "name": "null-guard-fix",
        "steps": [{"tool": "git", "action": "checkout"},
                  {"tool": "editor", "action": "replace"}],
        "positive_cases": [{"case": "payments"}],
    },
    "run_artifacts": [{"kind": "script", "body": "run.sh"}],
    "expert_annotations": [{"note": "reviewed"}],
    "privacy_policy": {"private_markers": ["tenant"]},
}


# --- the kernel path ---------------------------------------------------------


def test_arena_full_payload_reaches_the_kernel_with_its_quarantine_ledger(runtime):
    """Only the kernel judges a match it distrusts and says so out loud."""

    result = runtime.execute(ARENA, arena_request())
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    assert "ENGINE:legacy" not in result.reasons

    matches = result.output["pairwise_results"]["matches"]
    assert matches and all("quarantined" in item for item in matches)
    analysis = result.output["failure_analysis"]
    assert analysis["measured"] is True
    assert "quarantinedMatches" in analysis
    # The grader's half exists as a separate structure, which is the property
    # the legacy engine cannot express at all.
    assert result.output["arena_runs"]["taskSecrets"]


def test_gym_full_payload_reaches_the_kernel_with_a_frozen_acceptance_digest(runtime):
    """The digest frozen at registration is the kernel's whole reason to exist."""

    result = runtime.execute(GYM, gym_request())
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons

    digests = result.output["golden_artifacts"]["acceptanceDigests"]
    assert digests and all(value for value in digests.values())
    assert result.output["scorecards"]
    assert result.output["gym_runs"]["toolchainFingerprint"]


def test_curator_full_payload_reaches_the_kernel_with_recomputed_clusters(runtime):
    result = runtime.execute(CURATOR, curator_request())
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons

    clusters = result.output["failure_cluster"]
    assert clusters["stateDigest"]
    assert clusters["clusterCount"] >= 1
    # One candidate per cluster, each carrying the reasons it is not promotable.
    assert all("blockers" in item for item in result.output["improvement_candidate"])


def test_demonstration_full_payload_reaches_the_kernel_with_promotion_blockers(runtime):
    result = runtime.execute(DEMO, demonstration_request())
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons

    draft = result.output["skill_draft"]
    assert draft["autoPromoted"] is False
    assert "promotionBlockers" in draft
    assert result.output["trigger_examples"]["negativeCount"] >= 1


# --- the legacy path ---------------------------------------------------------


@pytest.mark.parametrize(
    ("skill", "payload"),
    [(ARENA, LEGACY_ARENA), (GYM, LEGACY_GYM), (CURATOR, LEGACY_CURATOR), (DEMO, LEGACY_DEMO)],
)
def test_a_legacy_shaped_payload_falls_through_with_a_recorded_reason(runtime, skill, payload):
    """A caller who was talking to the legacy engine correctly still gets an answer."""

    result = runtime.execute(skill, payload)
    assert result.error is None, result.to_dict()
    assert result.output
    assert "ENGINE:legacy" in result.reasons
    assert "ENGINE:kernel" not in result.reasons
    unmapped = [item for item in result.reasons
                if item.startswith("KERNEL_INPUT_UNMAPPED:") or item == "KERNEL_NOT_APPLICABLE"]
    assert unmapped, result.reasons
    # The declared output set is still complete, so the fallback is a real
    # answer rather than a stub.
    assert set(result.output) == set(SKILL_SPECS[skill].outputs)


def test_the_minimal_payloads_the_kernel_suite_pins_still_fall_through(runtime):
    """The exact payloads in test_kernel.py; they are a contract, not a sample."""

    cases = {
        CURATOR: {"run_incidents": [{"code": "x"}]},
        GYM: {"benchmark_repositories": [{"id": "r"}], "golden_task_specs": [{"id": "t"}]},
    }
    for skill, payload in cases.items():
        result = runtime.execute(skill, payload)
        assert result.error is None, (skill, result.to_dict())
        assert "ENGINE:legacy" in result.reasons


# --- what the adapters derive, and what they refuse to invent ----------------


def test_the_curator_adapter_derives_the_tenant_its_signals_already_declare(runtime):
    """A tenant named by every incident is a derivation, not an invention."""

    payload = curator_request()
    incidents = dict(payload["run_incidents"])
    tenant = incidents.pop("tenantId")
    incidents["incidents"] = [{**item, "tenantId": tenant} for item in incidents["incidents"]]
    payload["run_incidents"] = incidents

    request = kernel_bridge.BRIDGES[CURATOR].request_for(payload)
    assert request["run_incidents"]["tenantId"] == tenant
    result = runtime.execute(CURATOR, payload)
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons


def test_the_curator_adapter_refuses_to_invent_a_tenant(runtime):
    """No tenant anywhere is a gap to record, not a default to make up."""

    payload = curator_request()
    incidents = dict(payload["run_incidents"])
    del incidents["tenantId"]
    incidents["incidents"] = [{key: value for key, value in item.items() if key != "tenantId"}
                              for item in incidents["incidents"]]
    payload["run_incidents"] = incidents

    assert kernel_bridge.BRIDGES[CURATOR].request_for(payload) == {}
    result = runtime.execute(CURATOR, payload)
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons
    assert result.error is None


@pytest.mark.parametrize(
    ("section", "field"),
    [("arena_task_set", "repoSnapshotSha"), ("fixed_environments", "fingerprint")],
)
def test_the_arena_adapter_will_not_rebuild_a_control_from_what_it_controls(section, field):
    """Both values sit on every submission; copying them defeats their own check."""

    payload = arena_request()
    payload[section] = {key: value for key, value in payload[section].items() if key != field}
    assert kernel_bridge.BRIDGES[ARENA].request_for(payload) == {}


def test_the_gym_adapter_will_not_invent_a_toolchain_fingerprint():
    payload = gym_request()
    payload["fixed_images"] = {}
    assert kernel_bridge.BRIDGES[GYM].request_for(payload) == {}


def test_the_gym_adapter_refuses_rather_than_dropping_a_misshaped_optional_section():
    """Dropping the chaos scenarios would make readiness look better than it is."""

    payload = gym_request()
    payload["chaos_scenarios"] = [{"id": "executor-crash"}]
    assert kernel_bridge.BRIDGES[GYM].request_for(payload) == {}


def test_the_demonstration_adapter_will_not_infer_the_permission_profile():
    """allowedTools built from the tools used is a check that can never fail."""

    payload = demonstration_request()
    payload["privacy_policy"] = {key: value
                                 for key, value in payload["privacy_policy"].items()
                                 if key != "allowedTools"}
    assert kernel_bridge.BRIDGES[DEMO].request_for(payload) == {}


# --- the legacy engine describes itself --------------------------------------


def test_the_legacy_arena_says_its_scores_are_self_reported(runtime):
    result = runtime.execute(ARENA, LEGACY_ARENA)
    analysis = result.output["failure_analysis"]
    assert analysis["scoring_method"] == "self-declared-quality"
    assert analysis["measured"] is False
    assert "declared `quality` field" in analysis["method_note"]
    assert all(run["measured"] is False for run in result.output["arena_runs"])
    assert result.output["promotion_candidate"]["requires_independent_review"] is True
    assert "declared `quality` field" in result.output["promotion_candidate"]["reason"]


def test_the_legacy_gym_says_nothing_ran_and_nothing_was_frozen(runtime):
    result = runtime.execute(GYM, LEGACY_GYM)
    assert all(run["status"] == "NOT_RUN" for run in result.output["gym_runs"])
    assert all(run["acceptance_frozen"] is False for run in result.output["gym_runs"])
    assert "not frozen at route registration" in result.output["gym_runs"][0]["acceptance_note"]
    assert result.output["scorecards"][0]["reason"] == "native runner not supplied"
    assert result.output["regression_trends"]["status"] == "NOT_RUN"


def test_the_legacy_curator_does_not_claim_a_reproducer_it_never_ran(runtime):
    result = runtime.execute(CURATOR, LEGACY_CURATOR)
    reproducer = result.output["reproducer"]
    assert reproducer["executed"] is False
    assert "no reproducer was executed" in reproducer["method_note"]
    candidate = result.output["improvement_candidate"]
    assert candidate["before_after_measured"] is False
    assert candidate["requires_curator"] is True
    # The exact-key clustering really is order independent, so it is left alone.
    reversed_rows = list(reversed(LEGACY_CURATOR["run_incidents"]))
    other = runtime.execute(CURATOR, {"run_incidents": reversed_rows})
    assert other.output["failure_cluster"] == result.output["failure_cluster"]


def test_the_legacy_demonstration_says_its_draft_has_no_tested_boundary(runtime):
    result = runtime.execute(DEMO, LEGACY_DEMO)
    draft = result.output["skill_draft"]
    assert draft["status"] == "DRAFT"
    assert draft["generalised"] is False
    assert draft["boundary_checked"] is False
    assert "no counterexample was evaluated" in draft["method_note"]


# --- the property the bridge exists for --------------------------------------


def test_a_kernel_domain_rejection_is_never_downgraded_to_a_legacy_success(runtime):
    """The single most important safety property of this module.

    The payload below is one the kernel reads perfectly: every field decodes,
    nothing is missing.  It then refuses it, because the contestant-visible
    task statement quotes 43 characters of the grader's reference solution -
    a benchmark that leaks its own answer measures nothing.

    The legacy engine cannot see that: it has no reference solution to compare
    against, so it would score both contestants off their declared `quality`
    and return a cheerful promotion candidate.  If a domain rejection fell back,
    installing the deeper engine would have made this result *worse* than
    leaving it alone, because the refusal would be invisible.
    """

    payload = arena_request()
    payload["arena_task_set"]["tasks"][0]["view"]["statement"] = (
        "start from grouped.setdefault(row.key, []).append(row)"
    )

    # The kernel really does read it: the adapter builds a full request.
    assert kernel_bridge.BRIDGES[ARENA].request_for(payload)

    result = runtime.execute(ARENA, payload)
    assert result.error is not None, result.to_dict()
    assert result.error.code == "BENCHMARK_LEAKAGE"
    assert result.error.details["engine"] == "kernel"
    assert result.output == {}
    assert "ENGINE:legacy" not in result.reasons
    # And the legacy engine would indeed have answered, with a promotion
    # candidate, had the rejection been allowed to fall through.
    assert runtime.execute(ARENA, LEGACY_ARENA).output["promotion_candidate"]["candidate_id"]


@pytest.mark.parametrize(
    ("skill", "mutate", "code"),
    [
        (
            CURATOR,
            lambda payload: payload["run_incidents"]["incidents"][0].update(
                {"tenantId": "tenant-somebody-else"}),
            "PRIVACY_BLOCKED",
        ),
        (
            DEMO,
            lambda payload: payload["privacy_policy"].update({"allowedTools": ["git"]}),
            "TOOL_DENIED",
        ),
    ],
)
def test_every_bridged_learning_skill_keeps_its_domain_rejections(runtime, skill, mutate, code):
    """One cross-tenant inbox, one tool outside the permission profile."""

    payload = {CURATOR: curator_request, DEMO: demonstration_request}[skill]()
    mutate(payload)
    result = runtime.execute(skill, payload)
    assert result.error is not None, result.to_dict()
    assert result.error.code == code
    assert result.error.details["engine"] == "kernel"
    assert "ENGINE:legacy" not in result.reasons


def test_the_routing_table_still_names_only_catalog_skills():
    report = kernel_bridge.engine_report()
    for skill in (ARENA, GYM, CURATOR, DEMO):
        assert skill in report["kernelServed"]
        assert report["rationales"][skill]
