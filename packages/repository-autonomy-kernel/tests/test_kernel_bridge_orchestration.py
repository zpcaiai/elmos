"""Bridged orchestration skills: the core forks, the legacy engine plans a fork.

`session-time-travel` is the clearest case in the package of a legacy handler
whose output *reads* like it did something. It returns a `forked_run` with a
fresh uuid4 and `status: PLANNED`; no stream is copied and no FORK event is
recorded, so the id names a run that does not exist. The kernel engine forks for
real, and the property that matters — the parent timeline is untouched — is
asserted here through the merged dispatcher rather than only in the core's own
unit tests.
"""

from __future__ import annotations

import pytest
import test_timetravel as core  # the core's own payload builders, not a second copy

from elmos_autonomy_kernel.adapters.memory import FixedClock
from elmos_autonomy_kernel.timetravel import verify_chain
from elmos_repository_autonomy.dispatcher import AutonomyRuntime
from elmos_repository_autonomy.models import Status


@pytest.fixture()
def runtime() -> AutonomyRuntime:
    return AutonomyRuntime()


def _stream():
    return core.settled_stream(FixedClock())


def _payload(**target):
    events = _stream()
    return events, {
        "run_event_stream": core.payloads(events),
        "target_point": {"atSequence": events[-1].sequence, **target},
    }


# --- the kernel path ---------------------------------------------------------


def test_a_fork_routes_to_the_kernel_and_leaves_the_parent_untouched(runtime):
    """The headline property. Legacy could not violate it because it never forked.

    A fork that mutates its parent destroys the only timeline anyone can audit,
    so the assertion is on the parent: same head sequence, same chain digest,
    same event payloads, after the fork has been taken.
    """

    events, payload = _payload(operation="fork", newRunId="run-forked")
    before_head = events[-1].sequence
    before_chain = events[-1].chain
    before_payloads = [event.to_payload() for event in events]

    result = runtime.execute("session-time-travel", payload)

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    assert result.status is Status.LOCAL_ENGINEERING_VALIDATED

    fork = result.output["forked_run"]
    assert fork["newRunId"] == "run-forked"
    assert fork["parentSequence"] == before_head
    assert fork["forkDigest"].startswith("sha256:")
    assert fork["eventCount"] >= before_head

    # The parent is untouched, and its chain still verifies on its own terms.
    assert events[-1].sequence == before_head
    assert events[-1].chain == before_chain
    assert [event.to_payload() for event in events] == before_payloads
    assert verify_chain(events) is True


def test_a_restore_is_the_default_reading_of_a_stream_with_no_target(runtime):
    """A payload that supplies a stream and no target means "as of now".

    That is a derivation from what the caller sent, not an invented default, so
    the bridge passes the payload through unchanged and lets the kernel apply it.
    """

    events = _stream()
    # Deliberately NOT core.good_request(): that helper injects a target_point,
    # and the whole point here is a payload that carries none.
    result = runtime.execute("session-time-travel",
                             {"run_event_stream": core.payloads(events)})

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    snapshot = result.output["session_snapshot"]
    assert snapshot["atSequence"] == events[-1].sequence
    assert snapshot["viewDigest"].startswith("sha256:")


def test_forking_past_the_head_is_refused_not_clamped(runtime):
    """A domain rejection, and it must not be downgraded to a legacy success.

    Silently clamping to the head would answer a question the caller did not
    ask, and the legacy engine would happily return a cheerful PLANNED fork for
    the same payload.
    """

    events = _stream()
    result = runtime.execute("session-time-travel", {
        "run_event_stream": core.payloads(events),
        "target_point": {"operation": "fork", "atSequence": events[-1].sequence + 5,
                         "newRunId": "run-forked"},
    })

    assert result.error is not None
    assert "ENGINE:legacy" not in result.reasons
    assert result.output == {}
    assert result.error.details.get("engine") == "kernel"


# --- the legacy path, now labelled -------------------------------------------


def test_a_legacy_shaped_stream_still_works_and_records_the_gap(runtime):
    """A caller talking to the old engine correctly does not break."""

    result = runtime.execute("session-time-travel", {
        "run_event_stream": [{"sequence_no": 1}], "checkpoints": [],
        "context_ledgers": [], "change_graph": {}, "artifacts": [],
    })

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert any(reason.startswith("KERNEL_INPUT_UNMAPPED:") for reason in result.reasons)
    assert result.output["session_snapshot"]["event_count"] == 1


def test_the_legacy_fork_now_says_it_did_not_fork(runtime):
    """`status: PLANNED` alone let a new_run_id read as a run that exists."""

    result = runtime.execute("session-time-travel", {
        "run_event_stream": [{"sequence_no": 1}], "checkpoints": [],
        "context_ledgers": [], "change_graph": {}, "artifacts": [],
    })

    fork = result.output["forked_run"]
    assert fork["status"] == "PLANNED"
    assert fork["forked"] is False
    assert fork["deterministic_run_id"] is False
    assert "does not exist yet" in fork["note"]


def test_the_legacy_continuity_report_does_not_claim_a_check_it_never_ran(runtime):
    """`resume_equivalence` echoes the caller's own flag; that must be visible."""

    result = runtime.execute("model-state-continuity", {
        "context_ledger": {"objective": "x"}, "run_state": {"state": "PAUSED"},
        "provider_event": {},
    })

    report = result.output["continuity_report"]
    assert report["resume_equivalence"] is True
    assert report["resume_equivalence_checked"] is False
    assert "echoes the caller's own" in report["note"]


# --- changegraph -------------------------------------------------------------

S0 = "sha256:" + "0" * 64
S1 = "sha256:" + "1" * 64
S2 = "sha256:" + "2" * 64
CONTENT = "sha256:" + "c" * 64


def _change(change_id, parents, before, after, *, start=1, end=2, path="src/a.py"):
    return {
        "changeId": change_id, "parents": list(parents),
        "snapshotBefore": before, "snapshotAfter": after, "justification": "REQ-1",
        "edits": [{"path": path, "region": {"startLine": start, "endLine": end},
                   "operation": "replace", "contentDigest": CONTENT,
                   "justification": "REQ-1"}],
    }


def _graph_payload(patches):
    return {"task_spec": {"id": "t"}, "repository_snapshot": {"sha256": S0},
            "patches": patches, "artifact_lineage": {}, "validation_results": []}


def test_a_real_cycle_is_now_detected_where_legacy_asserted_acyclic(runtime):
    """The headline: legacy returned `acyclic: True` without ever checking.

    The reported set must also be the cycle itself, not everything downstream of
    it - sending a caller to break a dependency that is not the problem is its
    own defect, and the core reports a strongly connected component plus a
    witness path for exactly that reason.
    """

    result = runtime.execute("changegraph-vcs", _graph_payload([
        _change("c-a", ("c-b",), S0, S1),
        _change("c-b", ("c-a",), S1, S2),
    ]))

    assert result.error is not None
    assert result.error.code == "CHANGEGRAPH_CYCLE"
    assert result.error.details["cyclicChangeIds"] == ["c-a", "c-b"]
    assert "ENGINE:legacy" not in result.reasons


def test_a_well_formed_change_set_routes_to_the_kernel(runtime):
    result = runtime.execute("changegraph-vcs", _graph_payload([
        _change("c-a", (), S0, S1),
        _change("c-b", ("c-a",), S1, S2, start=40, end=42),
    ]))

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    graph = result.output["change_graph"]
    assert graph["conflictReport"]["conflicts"] == []
    assert [node["changeId"] for node in result.output["change_node"]] == ["c-a", "c-b"]


def test_two_changes_on_overlapping_lines_are_reported_not_merged(runtime):
    """Silently merging overlapping edits is how a change set loses an author's work."""

    result = runtime.execute("changegraph-vcs", _graph_payload([
        _change("c-a", (), S0, S1, start=10, end=20),
        _change("c-b", ("c-a",), S1, S2, start=15, end=25),
    ]))

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    conflicts = result.output["change_graph"]["conflictReport"]["conflicts"]
    assert conflicts, "overlapping regions must surface as a conflict"
    assert {"c-a", "c-b"} == set(conflicts[0]["changeIds"])


def test_shapeless_patches_stay_with_legacy_rather_than_being_invented_into_changes(runtime):
    """A patch that states no region cannot be given one; that would fabricate a conflict."""

    result = runtime.execute("changegraph-vcs",
                             _graph_payload([{"summary": "tidy up", "status": "UNVERIFIED"}]))

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons


def test_the_legacy_graph_no_longer_claims_a_cycle_check_it_never_ran(runtime):
    result = runtime.execute("changegraph-vcs",
                             _graph_payload([{"summary": "tidy up"}]))

    graph = result.output["change_graph"]
    assert graph["acyclic"] is True
    assert graph["acyclic_checked"] is False
    assert graph["conflict_detection"] == "NOT_RUN"
    assert "not by a cycle check" in graph["acyclic_note"]


# --- incremental semantic index ----------------------------------------------


def _snapshot(**files):
    return {"sha256": "sha256:snapshot",
            "files": [{"path": path, "content": text} for path, text in sorted(files.items())]}


APP = "def main():\n    return helper()\n\n\ndef helper():\n    return 1\n"
LIB = "def shared():\n    return 2\n"


def test_an_inline_snapshot_routes_to_the_kernel(runtime):
    result = runtime.execute("incremental-semantic-index",
                             {"repository_snapshot": _snapshot(**{"src/app.py": APP})})

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    index = result.output["semantic_index"]
    assert index["snapshot_sha"] == "sha256:snapshot"      # the caller's own id
    assert index["content_digest"].startswith("sha256:")   # what the bytes hash to
    assert index["content_digest"] != index["snapshot_sha"]


def test_incremental_equals_full_where_it_is_actually_reachable():
    """The core's headline property, asserted at the layer where it holds.

    The core refuses a JSON ``priorIndex``: it cannot verify that a
    hand-assembled index is one it produced, and an incremental update against a
    forged prior is worse than a full rebuild. So incremental is reachable
    in-process, from a caller holding the Index object - not across this JSON
    dispatcher. The property is real; its reach is narrower than the v2 contract
    implies, and that is recorded rather than papered over.
    """

    from elmos_autonomy_kernel.semindex import build, incremental
    from elmos_repository_autonomy.kernel_bridge import _InlineSnapshotReader

    before = _InlineSnapshotReader({"src/app.py": APP, "src/lib.py": LIB})
    prior = build(before)

    after_files = {"src/app.py": APP, "src/lib.py": LIB + "\n\ndef added():\n    return 3\n"}
    after = _InlineSnapshotReader(after_files)

    updated, _delta = incremental(prior, after, ("src/lib.py",))
    rebuilt = build(after)
    assert updated.to_payload()["indexDigest"] == rebuilt.to_payload()["indexDigest"]


def test_a_json_previous_index_does_not_silently_become_a_full_rebuild(runtime):
    """It still answers - but it must not be labelled incremental.

    The adapter drops a prior it cannot pass through instead of forwarding
    something the core would reject, so the call succeeds as a full build.
    """

    snapshot = _snapshot(**{"src/app.py": APP})
    first = runtime.execute("incremental-semantic-index", {"repository_snapshot": snapshot})
    assert "ENGINE:kernel" in first.reasons

    second = runtime.execute("incremental-semantic-index", {
        "repository_snapshot": snapshot,
        "previous_index": first.output["semantic_index"],
        "change_set": ["src/app.py"],
    })

    assert second.error is None
    assert "ENGINE:kernel" in second.reasons
    assert second.output["semantic_index"]["indexDigest"] == \
        first.output["semantic_index"]["indexDigest"]


def test_a_snapshot_without_file_text_stays_with_legacy(runtime):
    """Paths with no content cannot be indexed by anything; the core is not asked."""

    result = runtime.execute("incremental-semantic-index",
                             {"repository_snapshot": {"sha256": "sha256:x",
                                                      "files": ["src/app.py"]}})

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons


def test_the_legacy_ir_compiler_cannot_report_compiled_by_omission(runtime):
    """It wraps symbols in {'preserve': True}; COMPILED must be asserted, not inferred.

    The old test keyed off `index.partial`, so an index that simply lacked the
    flag flipped the status to COMPILED. Failing closed is the fix: a caller has
    to positively state completeness.
    """

    result = runtime.execute("semantic-ir-compiler", {
        "repository_semantic_index": {"snapshot_sha": "sha256:s", "symbols": []},
        "task_spec": {"id": "t"},
        "source_framework_profile": {"language": "Python"},
        "target_profile": {"language": "Python"},
    })

    assert result.output["semantic_ir"]["status"] == "PARTIAL"
    assert "does not lower anything" in result.output["semantic_ir"]["status_note"]


# --- contract compatibility ---------------------------------------------------


def _decl(param_type: str, *, name: str = "pay", return_type: str = "Receipt"):
    return [{"name": name, "kind": "function", "visibility": "public",
             "returnType": return_type,
             "params": [{"name": "amount", "type": param_type,
                         "kind": "positional", "hasDefault": False}]}]


def _compat(baseline, candidate, **overrides):
    payload = {"baseline_contracts": baseline, "candidate_contracts": candidate,
               "consumer_inventory": [], "compatibility_policy": {"publicApiPolicy": "strict"}}
    payload.update(overrides)
    return payload


def test_parameter_variance_is_reasoned_about_not_flattened(runtime):
    """Narrowing a parameter breaks callers; widening it does not.

    The legacy engine marks any changed value `breaking: True`, so both of these
    came back identical. That is fail-closed, but it makes the report useless for
    deciding whether a release may go out.
    """

    narrowed = runtime.execute("contract-compatibility-engine",
                               _compat(_decl("number"), _decl("integer")))
    widened = runtime.execute("contract-compatibility-engine",
                              _compat(_decl("number"), _decl("any")))

    assert "ENGINE:kernel" in narrowed.reasons
    assert "ENGINE:kernel" in widened.reasons
    assert narrowed.output["breaking_changes"], "narrowing a parameter must break"
    assert widened.output["breaking_changes"] == [], "widening a parameter must not break"


def test_a_removal_is_breaking_and_the_adapter_plan_says_where_it_came_from(runtime):
    result = runtime.execute("contract-compatibility-engine", _compat(_decl("number"), []))

    assert "ENGINE:kernel" in result.reasons
    assert result.output["breaking_changes"]
    plan = result.output["adapter_plan"]
    assert plan["required"] is True
    assert plan["derivedFrom"] == "breakingChanges"


def test_compatibility_without_a_stated_policy_is_not_answered_by_the_core(runtime):
    """strict / deprecate-first / best-effort give different verdicts on one diff.

    Choosing one on the caller's behalf answers a question they did not ask, so
    the core is not asked and the call falls to the legacy engine. Note what that
    means here: the legacy engine cannot read a declaration list either, so the
    caller gets a structural refusal rather than a verdict. That is the honest
    outcome - no engine in this package will grade a diff against an unstated
    policy - and it is worth having pinned rather than discovered later.
    """

    result = runtime.execute("contract-compatibility-engine",
                             _compat(_decl("number"), _decl("integer"),
                                     compatibility_policy={}))

    assert "ENGINE:kernel" not in result.reasons
    assert result.error is not None


def test_a_legacy_shaped_contract_pair_still_works(runtime):
    """The old callers - two documents, no declarations - are untouched."""

    result = runtime.execute("contract-compatibility-engine", {
        "baseline_contracts": {"openapi": "3.0.0", "paths": {"/pay": {}}},
        "candidate_contracts": {"openapi": "3.0.0", "paths": {"/pay": {}}},
        "consumer_inventory": [], "compatibility_policy": {},
    })

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert result.output["compatibility_report"]["status"] in {"COMPATIBLE", "BLOCKED",
                                                               "BREAKING"}


def test_free_form_contracts_are_not_coerced_into_declarations(runtime):
    """Guessing which key is "really" the parameter list puts variance on a guess."""

    result = runtime.execute("contract-compatibility-engine",
                             _compat({"openapi": "3.0.0"}, {"openapi": "3.1.0"}))

    assert "ENGINE:kernel" not in result.reasons


# --- validation DAG -----------------------------------------------------------


def test_declared_dependencies_build_a_real_dag(runtime):
    """Legacy chained gates by list position; that describes the caller's typing order."""

    result = runtime.execute("validation-dag", {
        "task_spec": {"id": "t"}, "change_graph": {}, "repository_profile": {},
        "risk_profile": {},
        "test_catalog": [
            {"checkId": "build", "kind": "build", "required": True},
            {"checkId": "unit", "kind": "test", "requires": ["build"], "required": True},
            {"checkId": "lint", "kind": "lint", "required": True},
        ],
        "validation_budget": {"maxCost": 100, "maxChecks": 10},
    })

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons
    dag = result.output["validation_dag"]
    requires = {check["checkId"]: check["requires"] for check in dag["checks"]}
    assert requires["unit"] == ["build"]
    # lint declared no dependency, so it must not have inherited one from position
    assert requires["lint"] == []


def test_a_plan_with_no_budget_stays_with_legacy(runtime):
    """An absent budget is not an unlimited budget, and inventing one hides trimming."""

    result = runtime.execute("validation-dag", {
        "task_spec": {"id": "t"}, "change_graph": {}, "repository_profile": {},
        "risk_profile": {}, "test_catalog": [{"checkId": "build", "kind": "build"}],
    })

    assert result.error is None
    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons


def test_a_cyclic_check_graph_is_refused_and_not_downgraded(runtime):
    """A domain rejection: the legacy planner would have chained these happily."""

    result = runtime.execute("validation-dag", {
        "task_spec": {"id": "t"}, "change_graph": {}, "repository_profile": {},
        "risk_profile": {},
        "test_catalog": [
            {"checkId": "a", "kind": "test", "requires": ["b"]},
            {"checkId": "b", "kind": "test", "requires": ["a"]},
        ],
        "validation_budget": {"maxCost": 100, "maxChecks": 10},
    })

    assert result.error is not None
    assert "ENGINE:legacy" not in result.reasons
    assert result.output == {}


# --- layered-cache-fabric ----------------------------------------------------
#
# The bridge's one absolute rule for this skill: a hit must be provably the same
# computation.  Everything below is either that rule holding, or a case where the
# bridge declines to promote rather than guess a key part.


_SNAPSHOT = "sha256:" + "a" * 64
_POLICY = "sha256:" + "b" * 64


def _cache_payload(**over):
    payload = {
        "snapshot_hash": _SNAPSHOT,
        "task_spec_hash": "sha256:" + "c" * 64,
        "workflow_version": "wf-1.2.0",
        "skill_versions": {"lint": "1.0.0"},
        "policy_hash": _POLICY,
        "tool_schema_versions": {"ruff": "0.6.0"},
        "model_profile": "opus-5",
        "prompt_prefix_digest": "sha256:" + "d" * 64,
        "environment_fingerprint": "sha256:" + "e" * 64,
        "layer_config": {
            "tenantId": "local", "namespace": "build", "cacheClass": "deterministic",
        },
        "operation": {"operationId": "build-lint", "sideEffecting": False},
    }
    payload.update(over)
    return payload


_CANDIDATE = {
    "value": {"exitCode": 0},
    "computeCostMs": 4200,
    "deterministic": True,
    "producerId": "lint-run-1",
}


def test_a_stored_entry_is_served_back_to_an_identical_key(runtime):
    """The baseline: the fabric must actually cache, across two dispatches.

    This is the test that would have caught two separate configuration bugs that
    both looked like strictness.  The fabric was first pinned to a placeholder
    snapshot, so every key was rejected as STALE_SNAPSHOT; then it was bound with
    the core's fail-closed empty admission policy, so every class was refused as
    CLASS_NOT_CACHEABLE.  Both produced a cache that never hit while every
    individual guard looked correct in isolation.
    """

    stored = runtime.execute("layered-cache-fabric", _cache_payload(candidate=_CANDIDATE))
    assert "ENGINE:kernel" in stored.reasons
    assert stored.output["hit_miss"]["admissionDecision"]["admitted"] is True

    served = runtime.execute("layered-cache-fabric", _cache_payload())
    assert "ENGINE:kernel" in served.reasons
    assert served.output["hit_miss"]["outcome"] == "HIT"
    assert served.output["hit_miss"]["layer"] == "L2"
    assert served.output["cache_entry"]["producerId"] == "lint-run-1"


def test_a_key_part_v2_never_declared_still_separates_two_computations(runtime):
    """The reason this skill was promoted at all.

    The prompt prefix digest is one of the two parts the legacy key omits.  Two
    runs identical in every declared part but differing in prompt prefix are
    different computations; under the legacy key they share one entry and each
    serves the other's result.  Here the second one must miss.
    """

    runtime.execute("layered-cache-fabric", _cache_payload(candidate=_CANDIDATE))
    other = runtime.execute(
        "layered-cache-fabric",
        _cache_payload(prompt_prefix_digest="sha256:" + "9" * 64),
    )

    assert "ENGINE:kernel" in other.reasons
    assert other.output["hit_miss"]["outcome"] == "MISS"
    assert other.output["cache_entry"] is None


def test_an_incomplete_key_is_never_hashed_into_a_hit(runtime):
    """Seven parts is the legacy dialect, and the legacy cache is correct for it.

    The failure this prevents is not a wrong answer from the core - it is the
    core being handed an invented ninth part and producing a confident hit for a
    computation nobody identified.
    """

    payload = _cache_payload()
    del payload["environment_fingerprint"]
    result = runtime.execute("layered-cache-fabric", payload)

    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons


def test_the_v2_store_through_dialect_keeps_its_working_cache(runtime):
    """``value`` carries no measured cost and no determinism claim.

    Promoting it would mean inventing both, and the honest translation - an
    admission refused for COMPUTE_COST_UNMEASURED - would still turn a caller's
    working write into a non-write.  An explained downgrade is a downgrade.
    """

    result = runtime.execute(
        "layered-cache-fabric", _cache_payload(value={"exitCode": 0}))

    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons


def test_a_class_the_key_cannot_describe_is_bypassed_with_a_stated_reason(runtime):
    """The bridge's admission policy has to be reachable in both directions.

    A time-bound result's correctness depends on wall-clock freshness, which no
    part of the nine-part key captures.  The bridge does not list it as
    cacheable, and the refusal is reported rather than silently returned as an
    ordinary miss - "we will not cache this" and "we had nothing" are different
    facts.
    """

    result = runtime.execute("layered-cache-fabric", _cache_payload(
        layer_config={
            "tenantId": "local", "namespace": "build", "cacheClass": "time-bound",
        },
    ))

    assert "ENGINE:kernel" in result.reasons
    assert result.output["hit_miss"]["outcome"] == "BYPASS"
    assert result.output["hit_miss"]["reason"] == "CLASS_NOT_CACHEABLE"


def test_a_side_effecting_operation_is_never_served_from_cache(runtime):
    """A hit here would return the result of an action without performing it."""

    runtime.execute("layered-cache-fabric", _cache_payload(candidate=_CANDIDATE))
    result = runtime.execute("layered-cache-fabric", _cache_payload(
        operation={"operationId": "build-lint", "sideEffecting": True},
    ))

    assert result.output["hit_miss"]["outcome"] == "BYPASS"
    assert result.output["hit_miss"]["reason"] == "SIDE_EFFECTING_OPERATION"


def test_the_response_says_the_freshness_pin_was_derived_from_the_request(runtime):
    """The pin agrees with the key by construction, so it verifies nothing.

    ``provenance`` reports what the fabric is pinned to, which reads as an
    independent statement about the live tree.  Over this bridge it is the
    request's own hashes handed back, so STALE_SNAPSHOT cannot fire.  Reporting
    the pin without that caveat would let a reviewer read agreement as a check
    having passed.
    """

    result = runtime.execute("layered-cache-fabric", _cache_payload())
    provenance = result.output["provenance"]

    assert provenance["freshnessPin"] == "request-derived"
    assert provenance["repoSnapshotSha"] == _SNAPSHOT
    assert provenance["policyHash"] == _POLICY
    assert "STALE_SNAPSHOT" in provenance["freshnessPinNote"]


def test_the_response_says_the_metrics_cover_one_call(runtime):
    """A per-call fabric reports a hit rate of 0 or 1000 per mille and nothing else."""

    result = runtime.execute("layered-cache-fabric", _cache_payload())
    metrics = result.output["cache_metrics"]

    assert metrics["scope"] == "single-call"
    assert metrics["lookups"] == 1


def test_the_bridge_admission_policy_excludes_what_the_key_cannot_describe():
    """Pinned so that widening the set is a deliberate edit with a test to answer.

    Adding ``semantic`` here would make the fabric serve results across inputs
    it judged similar without ever checking that equivalence.  Adding
    ``time-bound`` would make staleness invisible.  Neither should be possible
    to do by accident.
    """

    from elmos_autonomy_kernel.cache import CacheClass
    from elmos_repository_autonomy.kernel_bridge import _BRIDGE_CACHEABLE_CLASSES

    assert _BRIDGE_CACHEABLE_CLASSES == frozenset(
        {CacheClass.DETERMINISTIC, CacheClass.ENVIRONMENT_BOUND})
    assert CacheClass.SECRET_BOUND not in _BRIDGE_CACHEABLE_CLASSES


# --- repository-census -------------------------------------------------------


_CENSUS_SNAPSHOT = {
    "sha256": "snap-abc123",
    "files": [
        {"path": "pyproject.toml", "content": "[project]\nname='x'\n"},
        {"path": "src/app.py", "content": "def main():\n    pass\n"},
        {
            "path": "tests/test_app.py",
            "content": "EXAMPLE = 'the word password appears in this fixture'\n",
        },
        {"path": "README.md", "content": "# x\n"},
    ],
}


def test_a_file_body_never_reaches_the_risk_surface(runtime):
    """Legacy substring-matches file *content* and reports a P1 on a word.

    The fixture below contains the word "password" in a test file. The legacy
    census reports it as a P1 secret-surface finding - verified directly against
    `analysis.census` - which is both a false positive and a route by which file
    bodies drive an output. The core computes the risk surface from path shape
    only.
    """

    from elmos_repository_autonomy.analysis import census as legacy_census

    legacy = legacy_census(
        {**_CENSUS_SNAPSHOT,
         "files": [{**f, "sha256": str(i)}
                   for i, f in enumerate(_CENSUS_SNAPSHOT["files"])]},
        None, snapshot_sha="snap-abc123",
    )
    assert [f["category"] for f in legacy["risk_map"]["findings"]] == ["secret-surface"]

    result = runtime.execute(
        "repository-census", {"immutable_repository_snapshot": _CENSUS_SNAPSHOT})
    assert "ENGINE:kernel" in result.reasons
    assert result.output["risk_map"]["riskSurface"] == []


def test_the_census_keeps_both_snapshot_identities(runtime):
    """The caller's id is what downstream staleness checks compare against.

    Replacing it with the digest the core computed over the bytes would leave
    every consumer comparing against a number that means something else. Both
    are reported.
    """

    result = runtime.execute(
        "repository-census", {"immutable_repository_snapshot": _CENSUS_SNAPSHOT})
    profile = result.output["repository_profile"]

    assert profile["snapshot_sha"] == "snap-abc123"
    assert profile["content_digest"].startswith("sha256:")
    assert profile["content_digest"] != profile["snapshot_sha"]


def test_a_caller_stated_sha_does_not_fail_the_census(runtime):
    """The core's SNAPSHOT_CHANGED guard is real, and forwarding here would break it.

    The reader is built *from* the payload, so its sha is a digest of the inline
    bytes under this package's scheme - never equal to the caller's own id.
    Forwarding the caller's sha as ``snapshotSha`` would raise SNAPSHOT_CHANGED
    on every request that states one: the placeholder-pin failure again, a guard
    that always fires.
    """

    result = runtime.execute(
        "repository-census", {"immutable_repository_snapshot": _CENSUS_SNAPSHOT})

    assert result.error is None
    assert "ENGINE:kernel" in result.reasons


def test_the_census_reports_what_its_counts_mean(runtime):
    """A count whose definition is unstated is one two readers disagree about
    while both believe they agree."""

    result = runtime.execute(
        "repository-census", {"immutable_repository_snapshot": _CENSUS_SNAPSHOT})
    profile = result.output["repository_profile"]

    assert profile["definitions"]
    assert profile["census_digest"].startswith("sha256:")


def test_a_snapshot_without_file_content_stays_with_legacy(runtime):
    """Nothing can census paths alone, and the core is given the text or not asked."""

    result = runtime.execute("repository-census", {
        "immutable_repository_snapshot": {"sha256": "s", "files": [{"path": "a.py"}]},
    })

    assert "ENGINE:legacy" in result.reasons
    assert "KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST" in result.reasons


# --- the cross-engine status downgrade ---------------------------------------
#
# A defect class, not a bug: the legacy handlers fold a verdict into the dispatch
# status, while the kernel reports the verdict in the outputs and returns
# SUCCEEDED for the computation.  Routing a skill to the kernel therefore turned
# BLOCKED into LOCAL_ENGINEERING_VALIDATED for callers who never asked for a
# different engine and cannot see that they got one.  `compile_ir` was the first
# instance and was caught by an unrelated test; these three were found by
# auditing every legacy handler that returns a non-validated status.


def test_a_budget_that_drops_a_required_check_does_not_report_as_validated(runtime):
    """The core makes SKIPPED first-class; the bridge was discarding it at the status.

    Four required checks trimmed for budget came back LOCAL_ENGINEERING_VALIDATED
    - the exact failure the SKIPPED modelling exists to prevent, arriving through
    the bridge instead of through the engine.
    """

    from elmos_repository_autonomy.models import Status

    result = runtime.execute("validation-dag", {
        "task_spec": {"id": "t"}, "change_graph": {}, "repository_profile": {},
        "risk_profile": {},
        "test_catalog": [
            {"checkId": f"c{i}", "kind": "test", "required": True} for i in range(5)
        ],
        "validation_budget": {"maxCost": 1, "maxChecks": 1},
    })

    assert "ENGINE:kernel" in result.reasons
    assert result.status == Status.BLOCKED
    assert "VALIDATION_PLAN_INCOMPLETE" in result.reasons
    assert any(item["required"] for item in result.output["validation_plan"]["skipped"])


def test_an_optional_check_trimmed_for_budget_is_not_a_block(runtime):
    """Blocking on every trim would make the budget unusable; only required counts."""

    from elmos_repository_autonomy.models import Status

    result = runtime.execute("validation-dag", {
        "task_spec": {"id": "t"}, "change_graph": {}, "repository_profile": {},
        "risk_profile": {},
        "test_catalog": [
            {"checkId": "build", "kind": "build", "required": True},
            {"checkId": "fuzz", "kind": "test", "required": False},
        ],
        "validation_budget": {"maxCost": 100, "maxChecks": 1},
    })

    assert result.status == Status.LOCAL_ENGINEERING_VALIDATED
    assert "VALIDATION_PLAN_INCOMPLETE" not in result.reasons


def test_a_blocking_contract_change_does_not_report_as_validated(runtime):
    """The verdict is the caller's own policy's, not a stricter one the bridge added."""

    from elmos_repository_autonomy.models import Status

    breaking = runtime.execute("contract-compatibility-engine",
                               _compat(_decl("number"), _decl("integer")))
    widened = runtime.execute("contract-compatibility-engine",
                              _compat(_decl("number"), _decl("any")))

    assert breaking.status == Status.BLOCKED
    assert "CONTRACT_CHANGE_BLOCKING" in breaking.reasons
    assert widened.status == Status.LOCAL_ENGINEERING_VALIDATED


def test_a_spec_with_a_blocking_ambiguity_does_not_report_as_validated(runtime):
    """A criterion with no check reference is a wish, and legacy called it a check."""

    from elmos_repository_autonomy.models import Status

    base = {"specId": "s", "version": "1.0.0", "objective": "Move checkout",
            "intent": "Stop calling the legacy pricing table.", "scope": ["src/a.py"]}
    snapshot = {"sha256": "snap-1", "paths": ["src/a.py"]}

    wish = runtime.execute("task-spec-delta-compiler", {
        "requirements": {**base,
                         "acceptanceCriteria": [{"id": "c2", "description": "it feels faster"}]},
        "repository_snapshot": snapshot,
    })
    checked = runtime.execute("task-spec-delta-compiler", {
        "requirements": {**base, "acceptanceCriteria": [
            {"id": "c1", "description": "totals match", "verifier_type": "test",
             "check_ref": "tests/t.py::x"}]},
        "repository_snapshot": snapshot,
    })

    assert wish.status == Status.BLOCKED
    assert "AMBIGUITY_BLOCKED" in wish.reasons
    assert checked.status == Status.LOCAL_ENGINEERING_VALIDATED


def test_the_block_hook_can_only_move_a_status_towards_blocked():
    """A hook that could clear a block would let the bridge overrule a verdict."""

    from elmos_repository_autonomy import kernel_bridge

    for spec in kernel_bridge.BRIDGES.values():
        if spec.blocked_when is None:
            continue
        # Every predicate returns a reason string or None; nothing else is a
        # legal return, so nothing can express "unblock".
        assert spec.blocked_when({}) is None


# --- every row is a recorded decision ----------------------------------------


def test_every_skill_is_routed_by_a_written_decision():
    """A row with no rationale reads as "nobody looked yet" whether or not anybody did.

    Routed rows carry their reasoning in ``BRIDGES``; unrouted ones carried
    nothing at all, so the ten still on the legacy engine were indistinguishable
    from an unfinished list. Three of them are decisions - promoting them would
    make the package worse - and that only counts if it is written down where an
    operator reads it.
    """

    from elmos_repository_autonomy import kernel_bridge

    report = kernel_bridge.engine_report()
    assert set(report["legacyServed"]) == set(kernel_bridge.LEGACY_RATIONALES)
    assert set(report["kernelServed"]) | set(report["legacyServed"]) == set(
        kernel_bridge.SKILL_SPECS)

    for skill, entry in kernel_bridge.LEGACY_RATIONALES.items():
        assert isinstance(entry["blocked"], bool), skill
        # Long enough to be an argument rather than a label.
        assert len(entry["reason"]) > 200, skill


def test_the_three_blocked_rows_are_the_ones_that_would_fabricate_an_outcome():
    """Pinned by name, so promoting one is a deliberate edit with a test to answer.

    Each of these would have the kernel produce a confident record of something
    that did not happen: a tool call that never ran, a sandboxed execution that
    never occurred, or a security gate that refuses every request because the
    controls it grades were never supplied.
    """

    from elmos_repository_autonomy import kernel_bridge

    blocked = {skill for skill, entry in kernel_bridge.LEGACY_RATIONALES.items()
               if entry["blocked"]}
    assert blocked == {
        "typed-tool-runtime",
        "two-phase-secretless-sandbox",
        "tiered-security-assurance",
    }
    assert not blocked & set(kernel_bridge.BRIDGES)


def test_the_router_says_an_unpriced_model_outranked_a_priced_one(runtime):
    """A model that declares no price is scored as free and wins on that alone.

    quality/(cost + latency/100000) with `cost_per_call` defaulting to 0 means
    the candidate with no price data outscores a better priced model by three
    orders of magnitude. The default is kept - callers depend on this handler
    answering - but the output now names every unpriced model and states that
    the ranking is not reproducible across hosts.
    """

    result = runtime.execute("phase-aware-model-router", {
        "step_profile": {"required_context": 1000},
        "model_capability_profiles": [
            {"model_id": "priced", "eval_status": "PASS", "max_context": 8000,
             "quality": 0.9, "cost_per_call": 0.02, "latency_ms": 900},
            {"model_id": "no-price", "eval_status": "PASS", "max_context": 8000,
             "quality": 0.5},
        ],
        "risk_profile": {}, "budget": {}, "provider_policy": {},
    })

    decision = result.output["routing_decision"]
    assert decision["chosen_model"] == "no-price"
    assert decision["unpriced_models"] == ["no-price"]
    assert decision["reproducible"] is False
    assert "outranks every priced model" in decision["scoring_note"]


# --- model-state-continuity --------------------------------------------------


_LEDGER = {
    "ledgerId": "led-1",
    "observations": [
        {"kind": "ENTITY_OBSERVED", "subjectId": "s1"},
        {"kind": "DECISION_TAKEN", "subjectId": "s2"},
    ],
}
_BINDING = {
    "taskSpecVersion": "1.0.0", "repoSnapshotSha": "sha256:" + "a" * 64,
    "workflowVersion": "wf-1", "policySnapshotHash": "sha256:" + "b" * 64,
    "workspaceId": "ws-1", "environmentId": "env-1", "permissionProfileId": "p-1",
}
_AT = "2026-09-01T00:00:00.000000Z"


def _continuity(**over):
    payload = {"context_ledger": _LEDGER, "binding": _BINDING, "captured_at": _AT}
    payload.update(over)
    return payload


def test_the_checkpoint_digest_is_the_same_for_two_identical_requests(runtime):
    """The property the pinned clock exists to preserve.

    ``Checkpoint.digest`` is taken over a payload that includes ``createdAt``,
    so binding a system clock would make two runs of an identical request
    produce two different digests - and `bound_clock`'s own docstring says that
    destroys the reproducibility this module exists for. Binding nothing fails
    every call instead. So the clock is pinned to an instant the caller states.
    """

    first = runtime.execute("model-state-continuity", _continuity())
    second = runtime.execute("model-state-continuity", _continuity())

    assert "ENGINE:kernel" in first.reasons
    digest = first.output["continuity_report"]["checkpointDigest"]
    assert digest.startswith("sha256:")
    assert digest == second.output["continuity_report"]["checkpointDigest"]


def test_an_unstated_instant_is_never_taken_from_the_wall_clock(runtime):
    """"When was this checkpoint taken" is a fact only the caller holds."""

    from elmos_repository_autonomy import kernel_bridge

    payload = _continuity()
    del payload["captured_at"]
    outcome = kernel_bridge.serve("model-state-continuity", payload)

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


def test_resume_equivalence_is_not_claimed_when_nothing_was_replayed(runtime):
    """The unfireable-check-reported-as-passed shape, caught before shipping.

    A divergence raises, so any report a caller can read is one where
    equivalence held - but it only held over the decisions actually replayed,
    and a caller who supplied none had nothing replayed. Reporting that as
    "resume verified" is what the legacy engine's echo already does.
    """

    result = runtime.execute("model-state-continuity", _continuity())
    report = result.output["continuity_report"]

    assert report["decisionsReplayed"] == 0
    assert report["resume_equivalence_checked"] is False
    assert report["resume_equivalence"] is None
    assert "not exercised" in report["resume_equivalence_note"]


def test_a_failover_that_would_change_the_permission_profile_is_refused(runtime):
    """Fail over the model, never the authority - and the refusal is not downgraded."""

    result = runtime.execute("model-state-continuity", _continuity(
        provider_event={"fromProvider": "a", "toProvider": "b",
                        "permissionProfileId": "p-WIDE"},
    ))

    assert result.error is not None
    assert result.error.code == "PROVIDER_FAILOVER_FAILED"
    assert "ENGINE:legacy" not in result.reasons


def test_a_v2_provider_event_keeps_the_legacy_engine_rather_than_being_filtered(runtime):
    """Forwarding a filtered copy would run the check against a subset.

    v2's provider event carries `previous_state`, `sequence_no`, `diverged` and
    `unknown_side_effect`; the core reads three different fields. Dropping the
    event would skip the failover check while still answering, and filtering it
    would check less than the caller described. Neither is acceptable, so the
    call stays where it can be answered whole.
    """

    from elmos_repository_autonomy import kernel_bridge

    outcome = kernel_bridge.serve(
        "model-state-continuity", _continuity(provider_event={"diverged": False}))

    assert outcome.served is False
    assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",)


def test_a_free_form_v2_ledger_stays_with_legacy(runtime):
    """A synthesised hash chain would verify against itself and prove nothing."""

    result = runtime.execute("model-state-continuity", {
        "context_ledger": {"objective": "ship", "completed": [], "next_step": "x"},
        "run_state": {"state": "EXECUTING"}, "agent_state": {}, "provider_event": {},
    })

    assert "ENGINE:legacy" in result.reasons
    # And the legacy path keeps saying it never verified anything.
    assert result.output["continuity_report"]["resume_equivalence_checked"] is False


def test_a_bridge_private_key_never_reaches_the_kernel(runtime):
    """`_captured_at` configures the binder and must not be dispatched.

    The kernel rejects unknown request fields, correctly - a silently ignored
    field is a caller who thinks they configured something. Stripping the
    underscore-prefixed keys in `serve` is what makes a request-configured
    binder possible at all, so it is pinned here rather than left implicit.
    """

    from elmos_repository_autonomy import kernel_bridge

    request = kernel_bridge.BRIDGES["model-state-continuity"].request_for(_continuity())
    assert request["_captured_at"] == _AT

    # And the call still succeeds, which it cannot do if the key is dispatched.
    result = runtime.execute("model-state-continuity", _continuity())
    assert result.error is None
    assert "ENGINE:kernel" in result.reasons


# --- phase-aware-model-router ------------------------------------------------


def _model(model_id, price, tier):
    return {"modelId": model_id, "tier": tier, "provider": "acme",
            "contextWindow": 200000, "maxOutput": 8192,
            "priceInputPerMtok": price, "priceOutputPerMtok": price,
            "capabilities": ["code"], "reliabilityPrior": "0.99", "deprecated": False}


def _route(**over):
    payload = {
        "step_profile": {
            "phase": "execute", "riskClass": "high",
            "candidateModelIds": ["cheap", "frontier"],
            "requiredCapabilities": ["code"],
            "estimatedInputTokens": 10000, "estimatedOutputTokens": 2000,
        },
        "model_registry": [_model("cheap", "1.00", "standard"),
                           _model("frontier", "15.00", "frontier")],
        "routing_policy": {"rules": [{
            "phase": "execute", "riskClass": "high", "minTier": "frontier",
            "requiredCapabilities": ["code"], "allowedProviders": ["acme"],
            "costCeiling": "5.00",
        }]},
    }
    payload.update(over)
    return payload


def test_money_crosses_the_bridge_as_an_exact_string_not_a_float(runtime):
    """Found by the result failing to serialise at all.

    The core prices in ``Decimal`` so two hosts cannot disagree about the same
    model, and three fields carry one out. ``Decimal`` is not JSON-serialisable,
    so a promoted result raised ``TypeError`` the moment anything serialised it.

    ``float()`` is the wrong repair twice over: it discards the exactness the
    ``Decimal`` exists for - a promotion made *for* reproducibility ending by
    making the number irreproducible - and this package's ``canonical_json``
    encodes floats whose repr is platform-dependent at the last digit.
    """

    import json
    from decimal import Decimal

    result = runtime.execute("phase-aware-model-router", _route())

    assert "ENGINE:kernel" in result.reasons
    json.dumps(result.to_dict())  # must not raise

    amount = result.output["estimated_cost"]["amount"]
    assert isinstance(amount, str)
    assert Decimal(amount) == Decimal("0.18000000")
    assert isinstance(result.output["routing_decision"]["projectedCost"], str)
    assert isinstance(result.output["usage_record"]["projectedCost"], str)


def test_the_policy_floor_decides_and_the_cheaper_model_loses(runtime):
    """A min-tier floor the legacy engine has no way to express."""

    result = runtime.execute("phase-aware-model-router", _route())

    assert result.output["routing_decision"]["modelId"] == "frontier"


def test_a_v2_profile_is_never_converted_into_core_units(runtime):
    """`cost_per_call` is a different unit and `eval_status` is a gate, not a prior.

    Those are the numbers the reproducible ranking rests on. Fabricating them
    would produce a decision that is deterministic, hashed and auditable, and
    computed from figures the bridge made up - worse than the float ranking it
    replaced, because it looks rigorous.
    """

    result = runtime.execute("phase-aware-model-router", {
        "step_profile": {"required_context": 1000},
        "model_capability_profiles": [
            {"model_id": "a", "eval_status": "PASS", "max_context": 8000, "quality": 0.9},
        ],
        "risk_profile": {}, "budget": {}, "provider_policy": {},
    })

    assert "ENGINE:legacy" in result.reasons
    assert result.output["routing_decision"]["reproducible"] is False


def test_a_profile_missing_one_load_bearing_number_stays_with_legacy(runtime):
    """Checked in the adapter so the caller gets an answer, not a decode error."""

    from elmos_repository_autonomy import kernel_bridge

    for missing in ("tier", "maxOutput", "priceInputPerMtok", "reliabilityPrior"):
        profile = _model("frontier", "15.00", "frontier")
        del profile[missing]
        payload = _route(model_registry=[_model("cheap", "1.00", "standard"), profile])
        outcome = kernel_bridge.serve("phase-aware-model-router", payload)
        assert outcome.served is False, missing
        assert outcome.reasons == ("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",), missing


def test_a_budget_the_bridge_cannot_read_is_not_treated_as_no_budget(runtime):
    """An absent budget is not an unlimited budget - same rule as validation-dag."""

    from elmos_repository_autonomy import kernel_bridge

    outcome = kernel_bridge.serve("phase-aware-model-router", _route(budget={"cap": 5}))
    assert outcome.served is False

    # Stated in the core's own shape, it is honoured.
    served = kernel_bridge.serve(
        "phase-aware-model-router", _route(budget={"remaining": "100.00", "currency": "USD"}))
    assert served.served is True
