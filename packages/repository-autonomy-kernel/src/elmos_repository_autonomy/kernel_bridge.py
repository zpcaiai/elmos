"""Route a v2 capability to the deep kernel engine, or explain why it did not.

Two implementations of the same 31-skill contract were built independently and
this package now holds both:

* ``elmos_repository_autonomy`` — the platform: durable store, external-world
  adapters, certification, deployment, HTTP surface, 32-table schema.
* ``elmos_autonomy_kernel`` — the capability core: the algorithms, the
  invariants, and a test per acceptance gate.

The dispatcher stays the single entry point.  This module decides, per skill,
which engine answers it, and the decision is *data* — a table with a written
rationale per row — rather than a fact you have to reverse-engineer from an
import graph.

Three rules make the delegation safe:

1. **A kernel failure is never downgraded to the legacy engine.** Falling back
   on failure would let the weaker implementation silently overturn a correct
   rejection, which is worse than having no kernel at all.  Only
   ``NOT_APPLICABLE`` — the kernel's way of saying "my input contract is not
   met" — falls through, and the reason is recorded.
2. **The declared output set is still enforced.** ``dispatcher.execute`` checks
   the emitted fields against ``SKILL_SPECS``; the bridge does not get an
   exemption, so a mapping that forgets a field fails loudly here rather than
   producing a half-shaped response downstream.
3. **Every answer says which engine produced it** via an ``ENGINE:kernel`` /
   ``ENGINE:legacy`` reason, so a caller reading a result never has to guess
   which of two implementations it is looking at.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from elmos_autonomy_kernel import _bind_all_capabilities
from elmos_autonomy_kernel import evidence as kernel_evidence
from elmos_autonomy_kernel.contracts import Status as KernelStatus
from elmos_autonomy_kernel.contracts import digest as kernel_digest
from elmos_autonomy_kernel.contracts import digest_bytes as kernel_digest_bytes
from elmos_autonomy_kernel.errors import KernelError as CoreKernelError
from elmos_autonomy_kernel.errors import KernelError as _KernelSideError
from elmos_autonomy_kernel.registry import dispatch as kernel_dispatch

from .catalog import SKILL_SPECS
from .errors import ErrorInfo, KernelError
from .kernel_store_adapter import DurableStoreEventStore, DurableStoreLeaseStore
from .models import Status, canonical_json, digest
from .security import ExecutionAuthority as _LegacyExecutionAuthority

__all__ = [
    "BridgeSpec", "BridgeOutcome", "BRIDGES", "serve", "engine_for", "engine_report",
    "DECODE_LEVEL_CODES",
]

_bind_all_capabilities()

#: Kernel statuses that mean "this engine produced an answer".
_ANSWERED = {KernelStatus.SUCCEEDED, KernelStatus.PARTIAL}

#: Failure codes that mean "the payload was not shaped the way this engine
#: wanted", as opposed to "the domain rule was violated".  The distinction is
#: the whole safety argument of the bridge: a domain rejection must stand, but a
#: shape mismatch is a gap in *this module's* translation and must not be
#: allowed to break a caller who was talking to the legacy engine correctly.
DECODE_LEVEL_CODES = frozenset({
    "MALFORMED_INPUT", "MISSING_REQUIRED_INPUT", "UNKNOWN_FIELD", "INPUT_TOO_LARGE",
})

_STATUS_MAP = {
    # The kernel's SUCCEEDED means "computed and verified locally", which is
    # exactly what this package calls LOCAL_ENGINEERING_VALIDATED.  Mapping it
    # to SUCCEEDED would over-claim: nothing external has run.
    KernelStatus.SUCCEEDED: Status.LOCAL_ENGINEERING_VALIDATED,
    KernelStatus.PARTIAL: Status.PARTIAL,
}


def _identity(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    return dict(payload)


def _rfc3339_now() -> str:
    """The moment this call is happening, in the kernel's timestamp format."""

    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _from_context(context: Any, name: str, default: Any = None) -> Any:
    """Read one field off a ``DispatchContext`` without importing the dispatcher.

    The dispatcher imports this module, so the dependency can only go one way.
    Duck typing here is the cost of keeping the routing table free of a cycle.
    """

    value = getattr(context, name, None)
    return default if value is None else value


@dataclass(frozen=True, slots=True)
class BridgeOutcome:
    """What the bridge decided, including when it decided not to answer.

    A plain ``None`` return would have thrown away the reason, and "the legacy
    engine answered" is not the same fact as "the legacy engine answered
    because the kernel could not read this payload".  The second one is a
    measurable gap; the first is invisible.
    """

    served: bool
    status: Status | None = None
    output: Mapping[str, Any] | None = None
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BridgeSpec:
    """One routing decision, with the evidence for it.

    ``rationale`` is not decoration.  Two engines implement every skill here;
    six months from now the only way to know whether a row is still the right
    call is to read what was actually wrong with the alternative when the
    decision was made.
    """

    skill_id: str
    rationale: str
    build_request: Callable[[Mapping[str, Any]], Mapping[str, Any]] = _identity
    map_outputs: Callable[[Mapping[str, Any], Mapping[str, Any]], Mapping[str, Any]] | None = None
    #: Adapters for the four store-backed skills need the ``DispatchContext`` -
    #: its tenant and its ``DurableStore`` - to build a request at all, which the
    #: payload alone cannot supply.  Kept as a second, optional hook rather than
    #: widened into ``build_request`` so that the dozen payload-only adapters
    #: above stay exactly as simple as their job is.
    build_request_with_context: (
        Callable[[Mapping[str, Any], Any], Mapping[str, Any]] | None
    ) = None
    #: Runs after the kernel has answered, to write that answer into the durable
    #: store.  Only the orchestrator uses it: the kernel's run is pure, and
    #: without this hook bridging it would trade the legacy engine's persistence
    #: for the kernel's depth.  It returns the outputs and a reason naming what
    #: it actually did, so "persisted" and "could not persist" are two different
    #: observable facts rather than one silent one.  A failure here is a failure
    #: of the call - see ``serve`` - never a quiet fallback to the legacy engine.
    #: Installs a process-scoped binding for the duration of one kernel call -
    #: the durable artifact store, the cache fabric.  It receives the *built
    #: request* as well as the context because a binding sometimes has to be
    #: constructed against the very inputs the call names: the cache fabric is
    #: pinned to a snapshot and a policy, and a fabric pinned to anything other
    #: than what the request states rejects every key it is handed.
    bind_stores: (
        Callable[[Any, Mapping[str, Any]], AbstractContextManager[None]] | None
    ) = None
    persist_outputs: (
        Callable[
            [Any, Mapping[str, Any], Mapping[str, Any]], tuple[Mapping[str, Any], str]
        ] | None
    ) = None
    #: Publishes something the kernel produced back onto the ``DispatchContext``
    #: so the *next* skill in the same dispatch can see it.
    #:
    #: Only the authority row needs this today, and the reason is sharp.  The
    #: legacy handler ends with ``c.authority = authority``; the kernel path
    #: skips that handler entirely, so a kernel-minted authority reached nothing
    #: downstream.  ``lazy-tool-loader`` then saw ``None`` and loaded no tools
    #: (broken, but fail-closed); ``typed-tool-runtime`` reads ``c.authority or
    #: ExecutionAuthority.from_payload(payload["execution_authority"])`` and fell
    #: through to *the caller's own claim in the next payload* - so a caller who
    #: minted a narrow authority and then presented a wide one got the wide one,
    #: and the kernel's only-ever-narrows guarantee became decorative.
    #:
    #: The hook runs after ``map_outputs`` and cannot fail the call: a context
    #: that could not be updated is reported as a reason, never swallowed and
    #: never turned into a fallback to the legacy engine, which would re-run a
    #: mint that already happened.
    publish_context: (
        Callable[[Any, Mapping[str, Any]], str | None] | None
    ) = None
    #: Restores a BLOCKED verdict the legacy handler raised and the core
    #: expresses as data instead.
    #:
    #: This exists because of a defect class this merge has now hit twice.  The
    #: kernel reports "this spec has a blocking ambiguity" or "this gate failed"
    #: *in the outputs*, and returns SUCCEEDED for the computation - which is
    #: correct for the kernel: it was asked to compile a spec and it compiled
    #: one.  The legacy handlers instead fold that verdict into the dispatch
    #: status.  Routing such a skill to the core without this hook silently
    #: converts a caller's BLOCKED into LOCAL_ENGINEERING_VALIDATED, which is a
    #: *safety signal* changing meaning because of an implementation swap the
    #: caller never asked for and cannot see.  ``compile_ir`` was the first
    #: instance and was caught only by an unrelated test.
    #:
    #: The predicate returns the reason to block on, or ``None``.  It can only
    #: move a status towards BLOCKED, never away from it.
    blocked_when: (
        Callable[[Mapping[str, Any]], str | None] | None
    ) = None

    def request_for(self, payload: Mapping[str, Any], context: Any = None) -> Mapping[str, Any]:
        if self.build_request_with_context is not None:
            return self.build_request_with_context(payload, context)
        return self.build_request(payload)

    def outputs_for(self, payload: Mapping[str, Any],
                    outputs: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.map_outputs is None:
            return dict(outputs)
        return dict(self.map_outputs(payload, outputs))


def _spec(skill_id: str, rationale: str, *, build_request=_identity,
          map_outputs=None, build_request_with_context=None,
          persist_outputs=None, bind_stores=None, blocked_when=None,
          publish_context=None) -> BridgeSpec:
    return BridgeSpec(skill_id=skill_id, rationale=rationale,
                      build_request=build_request, map_outputs=map_outputs,
                      build_request_with_context=build_request_with_context,
                      persist_outputs=persist_outputs, bind_stores=bind_stores,
                      blocked_when=blocked_when, publish_context=publish_context)


# --- input adapters ----------------------------------------------------------
#
# An adapter promotes a v2-shaped payload into a complete kernel request.  It
# may *derive* a field that is implied by what the caller already sent; it may
# never *invent* one.  Returning ``{}`` means "the information this engine needs
# is not in this payload", which routes the call to the legacy engine with the
# gap recorded.


def _elo_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Promote an elo payload, but only when it actually contains matches.

    This is the sharpest example of why the two engines differ.  Elo is defined
    over *pairwise* outcomes; the legacy payload is a flat list of per-candidate
    PASS/FAIL rows, which has no opponents in it at all.  You cannot derive a
    pairing from independent rows without inventing who played whom - which is
    precisely why the legacy implementation is a win-rate rescale wearing the
    name Elo rather than a rating system.

    So: a payload carrying real matches is promoted (deriving the taxonomy from
    the classes those matches already name, which is a derivation and not an
    invention); a payload of flat rows is left to the legacy engine, which now
    labels its own output honestly.
    """

    results = payload.get("arena_results")
    if not isinstance(results, Mapping) or not results.get("matches"):
        return {}
    request = {key: value for key, value in payload.items() if value is not None}
    if "task_taxonomy" not in request:
        classes = sorted({
            str(item.get("taskClass"))
            for item in results.get("matches", ())
            if isinstance(item, Mapping) and item.get("taskClass")
        })
        if not classes:
            return {}
        request["task_taxonomy"] = {"classes": classes}
    return request


def _section(value: Any) -> Mapping[str, Any] | None:
    """The value as a kernel section, or ``None`` if it is not one at all."""

    return value if isinstance(value, Mapping) else None


def _rows(section: Mapping[str, Any] | None, key: str) -> tuple[Any, ...]:
    """The named array inside a section, or ``()`` when it is absent or scalar."""

    container = section.get(key) if isinstance(section, Mapping) else None
    if container is None or isinstance(container, (str, bytes, Mapping)):
        return ()
    if not isinstance(container, Sequence):
        return ()
    return tuple(container)


def _arena_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Promote an arena payload only when the grader's half is really present.

    The kernel arena is built around a separation the legacy shape does not
    have: a ``TaskView`` the contestant sees and a ``TaskSecret`` — reference
    solution, hidden checks, minimum plausible wall clock — that it does not.
    A legacy ``arena_task_set`` is a flat list of task rows with a ``quality``
    number on them, so there is no secret half to hand over and nothing to
    derive one from.

    Three fields are deliberately *not* filled in here even though a plausible
    value is sitting in the payload:

    * ``fixed_environments.fingerprint`` and ``arena_task_set.repoSnapshotSha``
      could both be copied off the submissions, and that is exactly the point:
      the kernel compares every submission against them to catch a run that
      drifted off the frozen environment or the pinned snapshot.  Deriving the
      control from the thing it controls turns both checks into tautologies.
    * ``evaluation_protocol.minDifficultyClasses`` could be set to the number of
      classes the task set happens to cover, which would make "your benchmark is
      all easy tasks" unsayable.

    So the adapter is a gate, not a translator: a payload already carrying the
    frozen halves is passed through, and anything else goes to the legacy engine
    — which now states that its scores are self-reported.
    """

    task_set = _section(payload.get("arena_task_set"))
    candidates = _section(payload.get("agent_candidates"))
    environments = _section(payload.get("fixed_environments"))
    budgets = _section(payload.get("budgets"))
    protocol = _section(payload.get("evaluation_protocol"))
    if any(item is None for item in (task_set, candidates, environments, budgets, protocol)):
        return {}
    if not _rows(task_set, "tasks") or not _rows(candidates, "contestants"):
        return {}
    if not _rows(candidates, "submissions"):
        return {}
    if not task_set.get("repoSnapshotSha") or not environments.get("fingerprint"):
        return {}
    return {
        "arena_task_set": task_set,
        "agent_candidates": candidates,
        "fixed_environments": environments,
        "budgets": budgets,
        "evaluation_protocol": protocol,
    }


def _gym_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Promote a gym payload only when there is a recorded run to score.

    The legacy gym never runs anything: it emits one ``NOT_RUN`` row per
    repository-by-spec pair.  The kernel scores *recorded evidence* against an
    acceptance contract frozen at route registration, so it needs three things
    the legacy payload does not contain — a fixture digest per route, a
    toolchain fingerprint, and the per-step evidence of an actual run.

    Each of those is a reproducibility control, which is precisely why none of
    them is synthesised here.  A ``fixtureDigest`` computed from the repository
    rows would make "this run used a different fixture" undetectable; a
    ``toolchainFingerprint`` invented from the images section would do the same
    for environment drift; and an ``acceptance`` block assembled from the steps
    a run happens to report would freeze the acceptance *around the run*, which
    is the one thing the frozen digest exists to prevent.  The kernel already
    defaults a run's ``acceptanceDigest`` to its route's, so the adapter does
    not touch that either.

    An optional section (``expected_contracts``, ``chaos_scenarios``) that is
    present but not in kernel shape refuses the whole promotion rather than
    being dropped: silently discarding the chaos scenarios or the commercial
    thresholds would make the readiness verdict look better than the payload
    supports.
    """

    repositories = _section(payload.get("benchmark_repositories"))
    specs = _section(payload.get("golden_task_specs"))
    images = _section(payload.get("fixed_images"))
    if repositories is None or specs is None or images is None:
        return {}
    if not images.get("toolchainFingerprint"):
        return {}
    if not _rows(repositories, "repositories"):
        return {}
    if not _rows(specs, "routes") or not _rows(specs, "runs"):
        return {}
    request: dict[str, Any] = {
        "benchmark_repositories": repositories,
        "golden_task_specs": specs,
        "fixed_images": images,
    }
    for name in ("expected_contracts", "chaos_scenarios"):
        value = payload.get(name)
        if value is None:
            continue
        section = _section(value)
        if section is None:
            return {}
        request[name] = section
    return request


def _curator_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Promote a curator payload, deriving the inbox's tenant from its signals.

    This is the one adapter of the four with something honest to derive.  The
    kernel scopes an inbox to a tenant and refuses a signal belonging to another
    one; the v2 payload has no envelope-level tenant field, but every signal may
    declare its own.  Taking the first declared tenant is a derivation — the
    caller supplied it — and it deliberately does *not* soften the check: a
    payload mixing two tenants still reaches the kernel and is still rejected
    with ``PRIVACY_BLOCKED``, which is the outcome that matters.  Stamping the
    envelope tenant onto each signal instead would have made that impossible.

    ``run_incidents.repoSnapshotSha`` is left exactly as the caller sent it.  It
    is a pin, not data: the kernel skips the staleness comparison when it is
    absent, and inventing a pin from the snapshots the signals happen to carry
    would be answering a question the caller never asked.

    With no signal anywhere, or with no tenant declared by any of them, the
    request is empty and the legacy clustering engine answers.
    """

    incidents = _section(payload.get("run_incidents"))
    if incidents is None:
        return {}
    request: dict[str, Any] = {}
    signals: list[Mapping[str, Any]] = []
    for name, container in (("run_incidents", "incidents"),
                            ("user_corrections", "corrections"),
                            ("findings", "findings"),
                            ("telemetry", "anomalies")):
        value = payload.get(name)
        if value is None:
            continue
        section = _section(value)
        if section is None:
            return {}
        signals.extend(item for item in _rows(section, container) if isinstance(item, Mapping))
        request[name] = section
    if not signals:
        return {}
    for name in ("benchmark_results", "existing_skills", "curation"):
        value = payload.get(name)
        if value is None:
            continue
        section = _section(value)
        if section is None:
            return {}
        request[name] = section
    if not incidents.get("tenantId"):
        tenant = next((item["tenantId"] for item in signals if item.get("tenantId")), None)
        if tenant is None:
            return {}
        request["run_incidents"] = {**incidents, "tenantId": tenant}
    return request


def _demonstration_request(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Promote a demonstration payload only when it names its own boundary.

    The legacy payload is a single demonstration with a ``steps`` list and a
    ``privacy_policy`` holding substring ``private_markers``.  The kernel wants
    a set of demonstrations pinned to one snapshot, plus a permission profile:
    ``privacy_policy.allowedTools`` is the list a demonstration's tools are
    checked against, and a demonstration using anything outside it is refused
    with ``TOOL_DENIED``.

    That field is the reason this adapter derives nothing.  ``allowedTools``
    could be filled from the tools the demonstration itself uses, and the result
    would be a permission check that can never fail — the same defect as
    grading a submission against its own answer.  ``forbiddenValuePrefixes``
    cannot be translated from ``private_markers`` either: a marker matches
    anywhere in a value, a prefix only at the front, and quietly re-reading one
    as the other narrows a privacy rule the caller wrote.

    A caller who has counterexamples and a permission profile gets the kernel's
    promotion ladder; a caller with one recorded trace gets the legacy draft,
    which now says it has no tested boundary.
    """

    demonstration = _section(payload.get("validated_demonstration"))
    privacy = _section(payload.get("privacy_policy"))
    if demonstration is None or privacy is None:
        return {}
    if not _rows(demonstration, "demonstrations"):
        return {}
    if not demonstration.get("draftId") or not demonstration.get("repoSnapshotSha"):
        return {}
    if not privacy.get("tenantId") or not privacy.get("scope"):
        return {}
    if not _rows(privacy, "allowedTools"):
        return {}
    request: dict[str, Any] = {
        "validated_demonstration": demonstration,
        "privacy_policy": privacy,
    }
    for name in ("run_artifacts", "expert_annotations"):
        value = payload.get(name)
        if value is None:
            continue
        section = _section(value)
        if section is None:
            return {}
        request[name] = section
    return request


def _artifact_content(payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Re-encode the caller's own bytes into the kernel's content envelope.

    This is a derivation and not an invention: the legacy engine already turns
    the same value into bytes with the same ``canonical_json`` / UTF-8 rules, so
    the content address the kernel computes is the one the legacy engine would
    have computed.  Only the envelope around it is new.
    """

    content = payload.get("content")
    if content is None:
        return None
    if isinstance(content, Mapping):
        keys = set(content)
        if keys <= {"mediaType", "text", "base64"} and ("text" in keys) != ("base64" in keys):
            return dict(content)
    media_type = payload.get("media_type")
    if isinstance(content, bytes):
        return {"mediaType": str(media_type or "application/octet-stream"),
                "base64": base64.b64encode(content).decode("ascii")}
    if isinstance(content, str):
        return {"mediaType": str(media_type or "text/plain"), "text": content}
    try:
        return {"mediaType": str(media_type or "application/json"),
                "text": canonical_json(content).decode("utf-8")}
    except (TypeError, ValueError):
        return None


def _artifact_request(payload: Mapping[str, Any],
                      context: Any = None) -> Mapping[str, Any]:
    """Promote an artifact payload only when it names what the evidence is about.

    The kernel's whole reason for existing here is ``repo_snapshot.inputDigests``:
    evidence is bound to the exact inputs it was produced from, so evidence for
    snapshot A cannot later be cited for snapshot B.  A v2 payload that carries
    no input digests can be *made* to pass the kernel by handing it an empty
    tuple - and an empty binding verifies against anything, which is the
    forgery this capability is designed to make impossible.  So a payload with
    no input digests is left to the legacy engine, which now says out loud that
    its evidence is bound to nothing but its own bytes.

    The same refusal covers ``producedAt`` (the kernel reads no clock, so a
    missing timestamp is missing data, not a default of "now"), the evidence id,
    and ``security_label`` - guessing ``internal`` for content that was never
    labelled would pick a retention window and a cache scope on the producer's
    behalf.  Case is normalised, because "INTERNAL" and "internal" are the same
    label spelled two ways, not two different claims.

    ``tenantId`` is the one field taken from the dispatch context rather than the
    payload: the tenant a call runs under is a fact the runtime already holds.
    ``producedAt`` deliberately is *not* - ``_rfc3339_now()`` is sitting right
    there, and using it would stamp the moment of translation onto evidence that
    was produced at some other time, which is how stale evidence stops looking
    stale.
    """

    step = payload.get("producer_step")
    snapshot = payload.get("repo_snapshot")
    if not isinstance(step, Mapping) or not isinstance(snapshot, Mapping):
        return {}
    digests = snapshot.get("inputDigests")
    if not isinstance(digests, (list, tuple)) or not digests:
        return {}
    if not isinstance(snapshot.get("snapshotSha"), str):
        return {}
    tenant_id = step.get("tenantId") or _from_context(context, "tenant_id")
    required = ("stepId", "producerId", "environmentFingerprint",
                "producedAt", "evidenceId", "claim", "kind")
    if tenant_id is None or any(step.get(name) is None for name in required):
        return {}
    label = payload.get("security_label")
    version = payload.get("task_spec_version")
    if not isinstance(label, str) or not isinstance(version, str):
        return {}
    content = _artifact_content(payload)
    if content is None:
        return {}
    known = (*required, "outcome")
    return {
        "producer_step": {**{name: step[name] for name in known if name in step},
                          "tenantId": tenant_id},
        "content": content,
        "repo_snapshot": {"snapshotSha": snapshot["snapshotSha"],
                          "inputDigests": list(digests)},
        "task_spec_version": version,
        "security_label": label.lower(),
    }


def _release_gate_request(payload: Mapping[str, Any],
                          context: Any = None) -> Mapping[str, Any]:
    """Promote a release payload only when its evidence bundle is already sealed.

    Everything this gate decides is downstream of one fact: whether the evidence
    bundle verifies under a key the caller does not hold.  A v2 payload lists
    artifact hashes instead, and there is no honest way to turn a list of hashes
    into a sealed bundle - synthesising a seal would be forging the signature
    the gate exists to check - so an unsealed payload is left to the legacy
    engine.

    Two other translations are available and both are refused.  ``rollback_ready:
    true`` is a boolean, not a rollback plan; the kernel requires a *complete*
    plan with steps, and manufacturing one from a flag turns "somebody ticked a
    box" into "a rollback has been written down".  A legacy ``approvals`` list is
    not a waiver set: waivers carry an approver, a scope and an expiry, and
    inventing those would waive findings nobody agreed to waive.

    What *is* forwarded verbatim is ``completion_claim``.  Dropping it would be
    the quiet failure here - ``maxTurnsExhausted`` and ``interrupted`` can only
    block, so a claim the kernel cannot read must fail the whole translation
    rather than be discarded on the way through.
    """

    criteria = payload.get("acceptance_criteria")
    validation = payload.get("validation_results")
    artifacts = payload.get("artifacts")
    deployment = payload.get("deployment_results")
    if not isinstance(criteria, Mapping) or not isinstance(validation, Mapping):
        return {}
    if not isinstance(artifacts, Mapping) or not isinstance(deployment, Mapping):
        return {}
    if not isinstance(artifacts.get("bundle"), Mapping):
        return {}
    if any(criteria.get(name) is None
           for name in ("runId", "repoSnapshotSha", "decidedAt", "mandatoryGateIds")):
        return {}
    if not isinstance(validation.get("gateResults"), (list, tuple)):
        return {}
    request: dict[str, Any] = {
        "acceptance_criteria": dict(criteria),
        "validation_results": dict(validation),
        "artifacts": dict(artifacts),
        "deployment_results": dict(deployment),
    }
    for name in ("completion_claim", "approvals"):
        if name in payload:
            request[name] = payload[name]
    return request


def _task_spec_version(value: Any) -> str | None:
    """The spec version the caller already stated, or nothing."""

    if isinstance(value, str):
        return value if 0 < len(value) <= 64 else None
    if isinstance(value, Mapping):
        for name in ("version", "id", "hash"):
            candidate = value.get(name)
            if isinstance(candidate, str) and 0 < len(candidate) <= 64:
                return candidate
    return None


def _verification_mesh_request(payload: Mapping[str, Any],
                               context: Any = None) -> Mapping[str, Any]:
    """Promote a verification payload only when its verdicts have verifiers.

    A legacy ``validation_dag`` is a list of self-reported status rows.  It has
    no verifier identity in it at all, so there is nothing to check independence
    against - and the tempting fix, giving every row an ``independenceClass`` of
    ``"default"``, would make every verifier maximally independent of every
    other one and of the thing they are checking.  That is not a translation
    gap; it is the exact failure the mesh exists to prevent, so a verdict
    without a verifier ends the promotion.  Inventing a quorum policy is the
    same defect one level up: ``requiredVerifiers: 1`` would let a single
    unopposed row carry a consensus.

    Two derivations are genuine.  ``repository_snapshot.sha256`` and
    ``snapshotSha`` are the same digest under two names, and a task spec's own
    ``version`` is the version the caller already declared.
    """

    change_set = payload.get("change_set")
    dag = payload.get("validation_dag")
    snapshot = payload.get("repository_snapshot")
    policies = payload.get("policies")
    if not isinstance(change_set, Mapping) or not isinstance(dag, Mapping):
        return {}
    if not isinstance(snapshot, Mapping) or not isinstance(policies, Mapping):
        return {}
    if not isinstance(policies.get("quorum"), Mapping):
        return {}
    verdicts = dag.get("verdicts")
    if not isinstance(verdicts, (list, tuple)) or not verdicts:
        return {}
    for item in verdicts:
        if not isinstance(item, Mapping):
            return {}
        verifier = item.get("verifier")
        if not isinstance(verifier, Mapping) or verifier.get("independenceClass") is None:
            return {}
    sha = snapshot.get("snapshotSha") or snapshot.get("sha256")
    version = _task_spec_version(payload.get("task_spec"))
    if not isinstance(sha, str) or version is None:
        return {}
    return {
        "change_set": dict(change_set),
        "validation_dag": {"verdicts": list(verdicts)},
        "task_spec": version,
        "repository_snapshot": {"snapshotSha": sha},
        "policies": dict(policies),
    }


def _cost_eta_request(payload: Mapping[str, Any],
                      context: Any = None) -> Mapping[str, Any]:
    """Promote a cost payload only when the run, the sizing and the prices are real.

    Every field this adapter refuses to fabricate is one that would silently
    become a zero.  A missing ``pricing_profile`` prices a run at nothing; a
    missing ``sizeUnits`` invents the denominator the ETA is regressed on; a
    missing ``tokensUsed`` reports "no tokens" for a provider that returned no
    accounting.  The kernel is built to say ``null`` and ``measured: false``
    instead, which only works if this function does not fill the holes first.

    The sharpest refusal is the one that looks most harmless.
    ``repo_features.repoSnapshotSha`` could be copied from
    ``run_events.repoSnapshotSha`` in one line, and the kernel's ``STALE_SNAPSHOT``
    check would then never fire again - the check exists precisely because
    sizing a run from another snapshot's features is a guess wearing a
    measurement's clothes.

    ``model_tool_usage`` and ``cache_metrics`` are forwarded verbatim, never
    dropped: an empty usage record set prices out at zero and *looks* measured,
    so a shape the kernel cannot read has to fail the translation rather than
    vanish from it.
    """

    events = payload.get("run_events")
    features = payload.get("repo_features")
    pricing = payload.get("pricing_profile")
    if not isinstance(events, Mapping) or not isinstance(features, Mapping):
        return {}
    if not isinstance(pricing, Mapping):
        return {}
    if not isinstance(events.get("runId"), str):
        return {}
    if not isinstance(events.get("repoSnapshotSha"), str):
        return {}
    if not isinstance(features.get("repoSnapshotSha"), str):
        return {}
    if features.get("sizeUnits") is None:
        return {}
    if pricing.get("profileId") is None or pricing.get("version") is None:
        return {}
    prices = pricing.get("prices")
    if not isinstance(prices, (list, tuple)) or not prices:
        return {}
    request: dict[str, Any] = {
        "run_events": dict(events),
        "repo_features": dict(features),
        "pricing_profile": dict(pricing),
    }
    for name in ("historical_runs", "model_tool_usage", "cache_metrics"):
        if name in payload and payload[name] is not None:
            request[name] = payload[name]
    return request




# --- the four store-backed skills --------------------------------------------
#
# These four are the only bridged skills where the *legacy* side owns something
# the kernel does not: ``DurableStore`` persistence.  Their adapters therefore
# take the ``DispatchContext`` as well as the payload, because the tenant and the
# store are part of the request in a way no payload can express.  The rule about
# derivation is unchanged and matters more here than anywhere else: a fabricated
# fencing token, policy-snapshot hash, TTL or authority ceiling does not merely
# guess - it hands the kernel the exact value that makes its check pass, which is
# worse than not calling the kernel at all.


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _first(source: Mapping[str, Any], *names: str) -> Any:
    """First present, non-null value among ``names``.

    Used only for spelling: ``ttlSeconds`` and ``ttl_seconds`` are the same fact
    written by two teams.  Reading both is translation; substituting a value for
    an absent one would not be, and never happens here.
    """

    for name in names:
        if source.get(name) is not None:
            return source[name]
    return None


def _positive_token(value: Any) -> int | None:
    if isinstance(value, Mapping):
        value = value.get("value")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None
    return value


def _orchestrator_request(payload: Mapping[str, Any], context: Any) -> Mapping[str, Any]:
    """Promote a run payload once every fact the kernel refuses to assume is present.

    The kernel's orchestrator will not open a run without a task-spec version, an
    identified repository snapshot, a budget and a declared policy snapshot.  Each
    of those four is exactly the kind of field it would be easy - and wrong - to
    default here: a made-up ``snapshotHash`` turns the "unpolicied run is denied"
    check into a formality, and a made-up snapshot sha defeats ``STALE_SNAPSHOT``,
    which exists because a plan compiled against yesterday's tree is not a plan.
    So a payload missing any of them goes to the legacy engine and the gap is
    recorded.

    ``tenantId``/``accountId``/``runId`` *are* derived when absent, from the
    dispatch context.  That is not the same act: the context is the authority on
    which tenant this call is executing as, so reading it is translation, while
    inventing a policy hash would be assertion.
    """

    task_spec = _mapping(payload.get("task_spec"))
    workflow = _mapping(payload.get("workflow_definition"))
    snapshot = _mapping(payload.get("repository_snapshot"))
    budget = _mapping(payload.get("budget"))
    policy = _mapping(payload.get("policy_snapshot"))
    if None in (task_spec, workflow, snapshot, budget, policy):
        return {}
    if not task_spec.get("taskSpecVersion"):
        return {}
    if not snapshot.get("snapshotSha") or not policy.get("snapshotHash"):
        return {}
    spec = dict(task_spec)
    if not spec.get("tenantId"):
        spec["tenantId"] = str(_from_context(context, "tenant_id", "local"))
    if not spec.get("accountId"):
        spec["accountId"] = str(_from_context(context, "account_id", "local"))
    run_id = _from_context(context, "run_id")
    if not spec.get("runId") and run_id:
        spec["runId"] = str(run_id)
    return {
        "task_spec": spec,
        "workflow_definition": dict(workflow),
        "repository_snapshot": dict(snapshot),
        "budget": dict(budget),
        "policy_snapshot": dict(policy),
    }


def _persist_durable_run(context: Any, payload: Mapping[str, Any],
                         outputs: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    """Write the kernel's run into ``DurableStore``, or say plainly that it did not.

    This function is why the orchestrator row is a merge rather than a swap.  The
    kernel's registry entry point is deterministic and pure - it drives an
    in-memory event store on a fixed clock - so delegating to it and stopping there
    would have produced a deeper answer that nobody could find again after the
    process exited.  The legacy handler's persistence is the thing the kernel does
    not have, so the bridge supplies it, through the same ports adapter the lease
    kernel uses.

    Two ordering decisions carry the weight:

    * The durable run's *state* is advanced along the trajectory the kernel's
      ``RUN_STATE_CHANGED`` events describe, so ``DurableStore.replay_state`` -
      the store's own check that its materialised row agrees with its own log -
      keeps passing.  A state the legacy transition table refuses surfaces as an
      error instead of being dropped: two state machines disagreeing about a run
      is precisely the inconsistency the store exists to catch.
    * The kernel's hash-chained events are then appended verbatim under
      ``KERNEL_`` event types, keyed for idempotency by their own chain digest, so
      re-running the same request appends nothing and ``replay`` over what was
      stored rebuilds the identical view.

    If there is no store on the context the run is *not* persisted, and both the
    returned reason and the run itself say so.  Reporting success with nothing
    written would be the same defect this bridge exists to avoid.
    """

    run_output = dict(outputs.get("run") or {})
    store = _from_context(context, "store")
    if store is None:
        run_output["durable"] = {"persisted": False, "reason": "NO_DURABLE_STORE_IN_CONTEXT"}
        return ({**outputs, "run": run_output},
                "KERNEL_NOT_PERSISTED:NO_DURABLE_STORE_IN_CONTEXT")

    tenant_id = str(_from_context(context, "tenant_id", "local"))
    account_id = str(_from_context(context, "account_id", "local"))
    task_spec = dict(_mapping(payload.get("task_spec")) or {})
    workflow = dict(_mapping(payload.get("workflow_definition")) or {})
    snapshot = _mapping(payload.get("repository_snapshot")) or {}
    events = [dict(item) for item in outputs.get("run_events") or () if isinstance(item, Mapping)]

    idempotency_key = payload.get("idempotency_key")
    if not isinstance(idempotency_key, str) or not idempotency_key:
        idempotency_key = "kernel-run:" + digest({
            "runId": run_output.get("runId"),
            "definitionDigest": run_output.get("definitionDigest"),
            "policySnapshotHash": run_output.get("policySnapshotHash"),
            "repoSnapshotSha": run_output.get("repoSnapshotSha"),
        })

    row = store.create_run(
        tenant_id=tenant_id, account_id=account_id,
        task_spec_hash=str(task_spec.get("hash") or digest(task_spec)),
        workflow_version=str(run_output.get("workflowVersion", "2.0.0")),
        repo_snapshot_sha=str(snapshot.get("snapshotSha")) if snapshot.get("snapshotSha") else None,
        payload={"task_spec": task_spec, "workflow_definition": workflow, "engine": "kernel"},
        idempotency_key=idempotency_key,
    )
    run_id = str(row["run_id"])

    trajectory = [
        str((item.get("body") or {}).get("to"))
        for item in events
        if item.get("eventType") == "RUN_STATE_CHANGED" and (item.get("body") or {}).get("to")
    ]
    pending = trajectory
    if str(row["state"]) in trajectory:
        pending = trajectory[trajectory.index(str(row["state"])) + 1:]
    for target in pending:
        row = store.transition_run(run_id, target, tenant_id=tenant_id)

    # The legacy handler wrote a row per step into ``steps``.  Nothing in the
    # kernel's pure path does, and dropping it would quietly narrow what an
    # operator can query about a run - so the kernel's step views are upserted
    # with the state the kernel actually assigned them, not a hardcoded PENDING.
    for step in outputs.get("step_runs") or ():
        if not isinstance(step, Mapping) or not step.get("stepId"):
            continue
        store.upsert_step(
            run_id=run_id, step_id=str(step["stepId"]),
            step_type=str(step.get("requiredCapability") or "skill"),
            state=str(step.get("state", "PENDING")),
            attempt_no=int(step.get("attemptNo", 0) or 0),
            tenant_id=tenant_id,
        )

    log = DurableStoreEventStore(store, tenant_id=tenant_id, account_id=account_id)
    for event in events:
        chain = event.get("chain")
        key = f"kernel-event:{chain}" if isinstance(chain, str) else None
        log.append(run_id, event, idempotency_key=key)

    state_snapshot = {
        "engine": "kernel",
        "state": str(row["state"]),
        "checkpoints": list(outputs.get("checkpoints") or ()),
        "viewDigest": run_output.get("viewDigest"),
    }
    checkpoint = store.latest_checkpoint(run_id, tenant_id=tenant_id)
    if checkpoint is None or checkpoint.get("content_hash") != digest(state_snapshot):
        checkpoint = store.create_checkpoint(run_id, state_snapshot, tenant_id=tenant_id)

    run_output["durable"] = {
        "persisted": True,
        "runId": run_id,
        "tenantId": tenant_id,
        "state": str(row["state"]),
        "checkpointId": str(checkpoint["checkpoint_id"]),
        "eventCount": len(store.events_since(run_id, tenant_id=tenant_id)),
        "kernelEventCount": len(events),
        "stepCount": len(outputs.get("step_runs") or ()),
        "replayedState": store.replay_state(run_id, tenant_id=tenant_id),
    }
    return {**outputs, "run": run_output}, "KERNEL_PERSISTED"


def _publish_authority(context: Any, outputs: Mapping[str, Any]) -> str | None:
    """Put the authority the kernel minted onto the dispatch context.

    The legacy handler's last line is ``c.authority = authority``, and every
    later skill in the same dispatch reads it. The kernel path skipped that
    handler, so nothing downstream saw the narrowed authority - and the two
    readers fail in opposite directions:

    * ``lazy-tool-loader`` does ``allowed = set(authority.allowed_tools) if
      authority else set()`` and loads nothing. Broken, but fail-closed.
    * ``typed-tool-runtime`` does ``c.authority or
      ExecutionAuthority.from_payload(payload["execution_authority"])``. With
      the context empty the ``or`` reaches the caller's own claim in the next
      payload. A caller who mints an authority narrowed to ``echo`` and then
      presents one granting ``write-file`` is served the second, and the
      kernel's only-ever-narrows guarantee - the entire reason this row routes
      to the core - becomes decorative.

    The translation goes through ``ExecutionAuthority.from_payload`` on the
    kernel's *own* output rather than the request, so what lands on the context
    is what the kernel decided, not what was asked for. That output is
    camelCase; ``from_payload``'s snapshot branch reads snake_case, so the
    fields are renamed here. Nothing is added: every field comes from the
    minted authority.

    A failure to translate is reported as a reason and never raised. Raising
    would fail a mint that already succeeded, and falling back to the legacy
    engine would mint a *second* authority with a second issued-at. The context
    then stays empty, which is the state that was there before this hook
    existed - and the loader's fail-closed reading of it is the safe one.
    """

    minted = outputs.get("execution_authority")
    if not isinstance(minted, Mapping):
        return "KERNEL_AUTHORITY_NOT_PUBLISHED:NO_AUTHORITY_IN_OUTPUT"

    snapshot = {
        "environment_id": minted.get("environmentId"),
        "workspace_id": minted.get("workspaceId"),
        "permission_profile_id": minted.get("permissionProfileId"),
        "policy_snapshot_hash": minted.get("policySnapshotHash"),
        "fencing_token": minted.get("fencingToken"),
        "allowed_tools": list(minted.get("allowedTools") or ()),
        "network_scopes": list(minted.get("networkScopes") or ()),
        "secret_scopes": list(minted.get("secretBindings") or ()),
        # The kernel refuses a conversation-scoped subject outright, so a minted
        # authority can never carry one. Passing the subject through rather than
        # defaulting keeps that refusal legible instead of re-asserting it here.
        "authority_source": minted.get("subject") or "execution-environment",
    }
    root = minted.get("workspaceRoot")
    if isinstance(root, str) and root:
        snapshot["workspace_root"] = root

    try:
        context.authority = _LegacyExecutionAuthority.from_payload(snapshot)
    except Exception as exc:  # noqa: BLE001 - reported, never raised: see docstring
        return f"KERNEL_AUTHORITY_NOT_PUBLISHED:{type(exc).__name__}"
    return "KERNEL_AUTHORITY_PUBLISHED"


def _authority_request(payload: Mapping[str, Any], context: Any) -> Mapping[str, Any]:
    """Promote an authority payload only when the environment states its own ceiling.

    The kernel does not validate a supplied authority, it *mints* one: the
    environment declares what is grantable and the permission profile may only
    stay under it, so escalation is unrepresentable rather than merely rejected.
    That only means anything if the ceiling comes from the environment.  The
    legacy payload has no ``grantedTools`` and no ``ttlSeconds`` - it carries the
    profile's own ``allowed_tools`` and nothing else - and the tempting default is
    to set the ceiling equal to the request.  That would make every narrowing
    check pass by construction and every escalation look authorised.  Same for a
    default TTL: it decides when ``AUTHORITY_EXPIRED`` fires.  Both are refused.

    ``issued_at`` *is* derived from the current time when unstated, and that is
    not the same thing.  Minting happens at the moment of the call; "now" is the
    true value of that field, not a stand-in for one the caller withheld.
    """

    environment = _mapping(payload.get("environment"))
    profile = _mapping(payload.get("permission_profile"))
    if environment is None or profile is None:
        return {}
    token = _positive_token(payload.get("fencing_token"))
    if token is None:
        return {}
    ttl = _first(environment, "ttlSeconds", "ttl_seconds")
    granted = _first(environment, "grantedTools", "granted_tools")
    if ttl is None or granted is None:
        return {}
    workspace = _mapping(payload.get("workspace")) or {}
    workspace_id = _first(environment, "workspaceId", "workspace_id")
    if workspace_id is None:
        workspace_id = _first(workspace, "workspaceId", "id")
    policy_hash = _first(environment, "policySnapshotHash", "policy_snapshot_hash")
    if policy_hash is None:
        policy_hash = _first(profile, "policySnapshotHash", "policy_snapshot_hash")
    environment_id = _first(environment, "environmentId", "id")
    if workspace_id is None or policy_hash is None or environment_id is None:
        return {}

    env: dict[str, Any] = {
        "environmentId": environment_id,
        "workspaceId": workspace_id,
        "policySnapshotHash": policy_hash,
        "ttlSeconds": ttl,
        "grantedTools": granted,
    }
    for target, *names in (("pathScopes", "pathScopes", "path_scopes"),
                           ("networkScopes", "networkScopes", "network_scopes"),
                           ("secretBindings", "secretBindings", "secret_bindings"),
                           ("subject", "subject", "authority_source")):
        found = _first(environment, *names)
        if found is not None:
            env[target] = found

    profile_id = _first(profile, "permissionProfileId", "id")
    if profile_id is None:
        return {}
    prof: dict[str, Any] = {"permissionProfileId": profile_id}
    for target, *names in (("tools", "tools", "allowed_tools"),
                           ("pathScopes", "pathScopes", "path_scopes"),
                           ("networkScopes", "networkScopes", "network_scopes"),
                           ("secretBindings", "secretBindings", "secret_bindings"),
                           ("ttlSeconds", "ttlSeconds", "ttl_seconds")):
        found = _first(profile, *names)
        if found is not None:
            prof[target] = found

    request: dict[str, Any] = {
        "environment": env,
        "permission_profile": prof,
        "fencing_token": token,
        "issued_at": _first(payload, "issued_at") or _first(environment, "issuedAt")
        or _rfc3339_now(),
    }
    if workspace:
        request["workspace"] = {"workspaceId": workspace_id}
    tool_request = _mapping(payload.get("tool_request"))
    if tool_request is not None:
        # A legacy tool request names no effect, and the kernel's read/write split
        # is what decides whether a fencing token is even required.  Guessing
        # "read" for a write would skip that check, so an untranslatable request
        # routes the whole call to the legacy engine instead.
        if "toolId" not in tool_request:
            return {}
        request["tool_request"] = dict(tool_request)
    return request


def _policy_request(payload: Mapping[str, Any], context: Any) -> Mapping[str, Any]:
    """Promote a hook evaluation only when the caller names its hook point and snapshot.

    ``run_context.policySnapshotHash`` is the caller's statement of *which* policy
    it believes it is being judged against; the kernel recomputes the snapshot
    hash from the layers and refuses the decision if the two differ.  Computing
    the declared hash here from the same layers would make that comparison
    compare a value to itself.  Absent, it is refused.

    ``hookPoint`` is likewise required rather than mapped from the legacy
    ``hook_event.type``: an event type and a hook point are different vocabularies,
    and silently renaming one into the other would evaluate a policy at a place
    the caller never asked about.
    """

    hook_event = _mapping(payload.get("hook_event"))
    run_context = _mapping(payload.get("run_context"))
    layers = payload.get("policy_layers")
    if hook_event is None or run_context is None or layers is None:
        return {}
    hook_point = hook_event.get("hookPoint")
    declared = _first(run_context, "policySnapshotHash", "policy_snapshot_hash")
    if not hook_point or not declared:
        return {}
    context_payload: dict[str, Any] = {"policySnapshotHash": declared}
    for name in ("snapshotId", "approvalTtlSeconds"):
        if run_context.get(name) is not None:
            context_payload[name] = run_context[name]
    context_payload["now"] = run_context.get("now") or _rfc3339_now()
    request: dict[str, Any] = {
        "hook_event": {"hookPoint": hook_point,
                       "subject": dict(_mapping(hook_event.get("subject")) or {})},
        "policy_layers": layers,
        "run_context": context_payload,
    }
    step_context = payload.get("tool_or_step_context")
    if step_context is not None:
        request["tool_or_step_context"] = step_context
    return request


def _persist_policy_decision(context: Any, payload: Mapping[str, Any],
                             outputs: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    """Keep the legacy handler's durable audit row for a kernel decision.

    ``_handle_policy_hook_kernel`` writes every verdict into ``policy_decisions``
    and, when the context names a run, onto that run's event log.  That row is
    the only place a decision survives the response, so bridging to the deeper
    engine without carrying it over would have bought a better verdict at the
    price of no longer being able to prove one was made.

    The row records what the decision *was*; it grants nothing, exactly as in the
    legacy handler.
    """

    store = _from_context(context, "store")
    decision = _mapping(outputs.get("policy_decision"))
    if store is None or decision is None:
        return outputs, "KERNEL_NOT_PERSISTED:NO_DURABLE_STORE_IN_CONTEXT"

    tenant_id = str(_from_context(context, "tenant_id", "local"))
    run_id = _from_context(context, "run_id")
    evidence = _mapping(outputs.get("policy_evidence")) or {}
    explanation = evidence.get("explanation")
    reason = "; ".join(str(item) for item in explanation) if isinstance(
        explanation, (list, tuple)) else "policy evaluated"
    store.record_policy_decision(
        tenant_id=tenant_id, run_id=str(run_id) if run_id else None,
        event_type=str(decision.get("hookPoint", "HOOK")),
        decision=str(decision.get("decision", "DENY")),
        reason=reason or "policy evaluated",
        policy_hash=str(decision.get("policySnapshotHash", "")),
        payload=dict(decision),
    )
    if run_id and store.get_run(str(run_id), tenant_id=tenant_id) is not None:
        DurableStoreEventStore(store, tenant_id=tenant_id).append(
            str(run_id), dict(decision),
            idempotency_key=f"policy-decision:{decision.get('digest')}")
    return outputs, "KERNEL_PERSISTED"


def _lease_request(payload: Mapping[str, Any], context: Any) -> Mapping[str, Any]:
    """Promote a lease request, injecting the durable store as the kernel's ports.

    The lease kernel is the one capability that refuses to run without live ports:
    a fencing kernel with a private in-memory store answers "is this token still
    current?" confidently and always wrongly.  So the adapter hands it a
    :class:`DurableStoreLeaseStore` over the very store the legacy handler writes
    to - which is what makes the kernel's monotonic-across-release guarantee apply
    to the same lease rows the rest of the platform reads.

    A missing TTL is refused rather than defaulted.  The legacy handler quietly
    substitutes 60 seconds, and a TTL is not a formality: it decides the moment a
    stalled worker's lease becomes takeable, which is the whole subject of this
    skill.  A ``renew`` without the token being renewed, and a ``takeover``
    without a reason, are refused for the same reason - the kernel's checks on
    both are only meaningful against a value the caller actually holds.
    """

    store = _from_context(context, "store")
    if store is None:
        return {}
    workspace = _mapping(payload.get("workspace"))
    lease_policy = _mapping(payload.get("lease_policy"))
    if workspace is None or lease_policy is None:
        return {}
    workspace_id = _first(workspace, "workspaceId", "id")
    worker = payload.get("worker_identity")
    if isinstance(worker, str):
        owner_id: Any = worker
    elif isinstance(worker, Mapping):
        owner_id = _first(worker, "ownerId", "id", "worker_id")
    else:
        owner_id = None
    ttl = _first(lease_policy, "ttlSeconds", "ttl_seconds")
    if workspace_id is None or owner_id is None or ttl is None:
        return {}

    action = str(lease_policy.get("action", "acquire"))
    policy: dict[str, Any] = {
        "ttlSeconds": ttl,
        "issuedAt": lease_policy.get("issuedAt") or _rfc3339_now(),
        "action": action,
    }
    if action == "renew":
        held = _positive_token(_first(lease_policy, "fencingToken", "fencing_token"))
        if held is None:
            return {}
        policy["fencingToken"] = held
    if action == "takeover":
        reason = lease_policy.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            return {}
        policy["reason"] = reason
        previous = _first(lease_policy, "previousOwner", "previous_owner")
        if previous is not None:
            policy["previousOwner"] = previous

    tenant_id = str(_from_context(context, "tenant_id", "local"))
    account_id = str(_from_context(context, "account_id", "local"))
    request: dict[str, Any] = {
        "workspace": {"workspaceId": workspace_id},
        "worker_identity": {"ownerId": owner_id},
        "lease_policy": policy,
        "ports": {
            "lease_store": DurableStoreLeaseStore(store, tenant_id=tenant_id),
            "event_store": DurableStoreEventStore(
                store, tenant_id=tenant_id, account_id=account_id),
        },
    }
    for name in ("checkpoint", "side_effect_ledger"):
        if payload.get(name) is not None:
            request[name] = payload[name]
    return request


def _release_gate_outputs(payload: Mapping[str, Any],
                          outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Keep the kernel's gate reasoning; refuse to let it issue P05 by itself.

    This is the one place where routing to the deeper engine would have *lost* a
    safety property, so the bridge holds the line rather than the engine.

    The legacy gate hard-codes ``attested: False`` and appends
    ``trusted-certification-engine-required`` to every decision: in this package
    P05_DEPLOYMENT_COMPLETE may only be issued by ``CertificationEngine``, which
    binds signed evidence, persisted customer acceptance and the T00-T08 case
    identities to the candidate digest.  The kernel's gate is strictly better at
    *blocking* - it treats NOT_RUN and SKIPPED as non-verdicts, demands a
    complete rollback plan, and expires waivers - but its own attestation rests
    on an HMAC seal whose key is process-local, so anything able to reach the
    process could mint a bundle that verifies.  Taking the kernel's reasoning
    and the legacy's ceiling narrows nothing and gives up nothing.

    So: every gate result, finding and reason the kernel produced is preserved
    verbatim, and only the attestation is capped, with the reason recorded in
    the payload rather than left for a reader to infer from a bare ``false``.
    """

    result = dict(outputs)
    attestation = dict(result.get("deployment_complete_attestation") or {})
    if attestation.get("attested") is True:
        attestation["attested"] = False
        attestation["kernelAttested"] = True
        attestation["gate"] = "P05_DEPLOYMENT_COMPLETE_NOT_ISSUED"
        attestation["withheldReason"] = (
            "the kernel gate accepted the release, but P05_DEPLOYMENT_COMPLETE is "
            "issued only by CertificationEngine, which binds signed evidence and "
            "persisted customer acceptance to the candidate digest; the kernel's "
            "own seal key is process-local and therefore not an external anchor"
        )
        attestation["requiredNext"] = "trusted-certification-engine"
        result["deployment_complete_attestation"] = attestation
    return result


@contextmanager
def _durable_artifact_store(context: Any, _request: Mapping[str, Any]) -> Iterator[None]:
    """Point the kernel's artifact writes at the durable, tenant-scoped store.

    The kernel's evidence module writes through a module-level default that is
    an in-memory, un-tenanted store unless something binds one.  Routing
    ``artifact-evidence-protocol`` to the kernel without this would have traded
    a real property for a better one: the kernel's *binding* of evidence to its
    input digests is much stronger, but its *storage* would have been a process
    dictionary, so the bytes would not survive the request and one tenant could
    read another's artifact.  Merging is supposed to keep both.

    The binding is scoped to the call and restored afterwards, including on the
    exception path - a bridge that leaves a tenant's store installed as the
    process default would leak exactly what it was installed to isolate.
    """

    store = getattr(context, "store", None)
    tenant = str(getattr(context, "tenant_id", "") or "")
    if store is None or not tenant:
        yield
        return

    from .kernel_store_adapter import DurableStoreArtifactStore

    previous = kernel_evidence.default_artifact_store()
    kernel_evidence.set_default_artifact_store(
        DurableStoreArtifactStore(store, tenant_id=tenant))
    try:
        yield
    finally:
        kernel_evidence.set_default_artifact_store(previous)



_CHANGE_SHAPE = frozenset({"changeId", "snapshotBefore", "snapshotAfter", "edits"})


def _changegraph_request(payload: Mapping[str, Any],
                         context: Any = None) -> Mapping[str, Any]:
    """Promote only when the patches are already changes, never by inventing edits.

    The legacy payload's ``patches`` are arbitrary mappings - the legacy engine
    only digests them, so nothing constrains their shape. The kernel needs a
    change: an id, a before and after snapshot digest, and edits carrying a path,
    a line region, an operation and a content digest. Manufacturing a line region
    or a before-digest for a patch that never stated one would let the graph
    "detect" conflicts between regions this adapter made up, and let an apply
    plan claim a before-state nobody recorded. That is worse than not answering.

    So a patch is forwarded when it already *is* a change, and the request is
    refused otherwise. ``target`` and ``semanticIndex`` ride along when present:
    the semantic index turns region-overlap detection into entity-level conflict
    detection, which is the whole reason the kernel takes one.
    """

    raw = payload.get("patches")
    if isinstance(raw, Mapping) or not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return {}
    changes = [item for item in raw if isinstance(item, Mapping)]
    if not changes or not all(_CHANGE_SHAPE <= set(item) for item in changes):
        return {}

    request: dict[str, Any] = {"changes": changes}
    lineage = payload.get("artifact_lineage")
    if isinstance(lineage, Mapping):
        # The lineage is where a caller states which change is being applied and
        # what the working tree currently holds; neither is derivable from the
        # changes themselves, so both are forwarded only when stated.
        if lineage.get("target"):
            request["target"] = lineage["target"]
        if isinstance(lineage.get("state"), Mapping):
            request["state"] = lineage["state"]
        if isinstance(lineage.get("semanticIndex"), Mapping):
            request["semanticIndex"] = lineage["semanticIndex"]
        if isinstance(lineage.get("entitySpans"), Mapping):
            request["entitySpans"] = lineage["entitySpans"]
        if isinstance(lineage.get("requireVerified"), bool):
            request["requireVerified"] = lineage["requireVerified"]
    return request


def _changegraph_outputs(payload: Mapping[str, Any],
                         outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Rename the kernel's camelCase onto the six declared v2 output fields.

    The conflict report has no v2 field of its own, and dropping it would hide
    the single most important thing this engine produces, so it rides inside
    ``change_graph`` where a reader of the graph will find it.
    """

    graph = dict(outputs.get("changeGraph") or {})
    graph["conflictReport"] = outputs.get("conflictReport")
    graph["gates"] = outputs.get("gates")
    mapped: dict[str, Any] = {
        "change_graph": graph,
        "change_node": outputs.get("changeNodes"),
        "change_edge": outputs.get("changeEdges"),
    }
    if outputs.get("mergePlan") is not None:
        mapped["merge_plan"] = outputs["mergePlan"]
    if outputs.get("revertPlan") is not None:
        mapped["revert_plan"] = outputs["revertPlan"]
    if outputs.get("provenanceCommit") is not None:
        mapped["provenance_commit"] = outputs["provenanceCommit"]
    return mapped



class _InlineSnapshotReader:
    """A kernel ``RepositoryReader`` over the files a v2 payload already carries.

    The capability core reads a repository through a port rather than a JSON
    blob, because a snapshot that can change under an in-flight run is the
    staleness bug the port exists to catch. The v2 ``repository_snapshot``
    carries its files inline, so wrapping exactly those bytes invents nothing -
    it is the same content, presented through the interface the core requires.

    The snapshot sha is computed from the supplied paths and their content
    digests rather than taken from the payload's own ``sha256`` field: a caller
    that mislabels its snapshot would otherwise get an index stamped with an id
    that does not describe it, and every downstream staleness check would
    compare against a lie. If the caller states a sha, ``handle`` compares the
    two and refuses on mismatch - which is the check working, not a bug.
    """

    __slots__ = ("_files", "_snapshot_sha")

    def __init__(self, files: Mapping[str, str]) -> None:
        self._files = dict(sorted(files.items()))
        self._snapshot_sha = kernel_digest({
            "files": [
                {"path": path, "digest": kernel_digest_bytes(text.encode("utf-8")),
                 "byteCount": len(text.encode("utf-8"))}
                for path, text in self._files.items()
            ]
        })

    @property
    def snapshot_sha(self) -> str:
        return self._snapshot_sha

    def list_paths(self) -> tuple[str, ...]:
        return tuple(self._files)

    def read_text(self, path: str) -> str:
        return self._files[path]

    def read_bytes(self, path: str) -> bytes:
        return self._files[path].encode("utf-8")

    def stat(self, path: str) -> Mapping[str, Any]:
        raw = self._files[path].encode("utf-8")
        return {"path": path, "digest": kernel_digest_bytes(raw),
                "byteCount": len(raw), "oversized": False}


def _inline_files(snapshot: Any) -> dict[str, str] | None:
    """Read a v2 repository snapshot's files, or ``None`` if it carries no text."""

    if not isinstance(snapshot, Mapping):
        return None
    raw = snapshot.get("files")
    if isinstance(raw, Mapping):
        pairs = [(key, value) for key, value in raw.items()]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        pairs = []
        for item in raw:
            if not isinstance(item, Mapping):
                return None
            path, content = item.get("path"), item.get("content")
            if not isinstance(path, str) or not isinstance(content, str):
                return None
            pairs.append((path, content))
    else:
        return None
    if not pairs or not all(isinstance(k, str) and isinstance(v, str) for k, v in pairs):
        return None
    return dict(pairs)



#: v2 writes criteria in snake_case with ``id``/``description``; the core reads
#: camelCase with ``criterionId``/``statement``. Renaming a field is a
#: translation. Supplying one that is absent is not - see ``_criterion``.
_CRITERION_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("criterionId", ("criterionId", "id")),
    ("statement", ("statement", "description")),
    ("verifierType", ("verifierType", "verifier_type")),
    ("checkRef", ("checkRef", "check_ref")),
    ("must", ("must",)),
)


def _criterion(item: Any) -> Mapping[str, Any] | None:
    """Translate one v2 acceptance criterion, or ``None`` if it is not one.

    ``checkRef`` is copied when stated and left absent otherwise. That absence
    is the entire point: the core treats a criterion with no check reference as
    unverifiable and reports it in ``untracedCriterionIds``, which is the honest
    reading of "we said what good looks like and never said who decides". The
    legacy engine defaults every criterion's verifier to ``deterministic`` and
    carries no reference at all, so every wish is reported as a check.
    """

    if not isinstance(item, Mapping):
        return None
    out: dict[str, Any] = {}
    for core_name, sources in _CRITERION_KEYS:
        for source in sources:
            if source in item and item[source] is not None:
                out[core_name] = item[source]
                break
    if "criterionId" not in out or "statement" not in out:
        return None
    return out


def _taskspec_request(payload: Mapping[str, Any], context: Any = None) -> Mapping[str, Any]:
    """Promote only a caller who states the five fields the core compiles from.

    **What legacy actually does with a delta.** ``changed_fields`` is a literal
    constant: when the previous spec's hash differs at all, it returns
    ``["objective", "acceptance_criteria", "constraints", "deliverables"]`` -
    those four, every time, whatever moved. ``cache_invalidation`` is that same
    list and ``affected_nodes`` is *every* criterion. So the delta compiler
    computes no delta; it reports "everything" or "nothing", and a one-word
    objective edit invalidates the entire cache. The core diffs the two specs
    and reports the criteria added, removed and changed, the scope paths entered
    and left, and the steps those actually invalidate.

    Its ambiguity register is four hardcoded field names tested for emptiness -
    a field *declared but empty* is HIGH, a field entirely absent is not
    ambiguous at all - so ``scope: []`` blocks and no scope key passes. And a
    requirements object with no acceptance criteria is given a fabricated one
    (``schema-valid``, "Output satisfies the typed contract") which then reports
    as a satisfied criterion; the core has no way to express that, because a
    criterion nobody wrote cannot be a criterion anybody agreed to.

    **What promotion requires, and why none of it is derivable.** ``specId`` and
    ``version`` are identities: the delta is computed *between* two specs, so an
    id the bridge minted from the objective would make two unrelated specs with
    the same objective diff against each other, which is the legacy id scheme
    and the thing being replaced. ``intent`` is the free text every ambiguity
    detector reads; setting it to the objective would hand the detectors the one
    string already known to be well-formed and guarantee a clean register.
    ``scope`` must be non-empty because the scope diff is half the delta.
    A caller stating fewer than these keeps the legacy compiler, and the gap is
    recorded.

    Constraints and assumptions are forwarded only in the core's own shape. A
    v2 caller who states them in some other shape is *refused* rather than
    having them dropped: a spec compiled without the constraints the caller
    wrote is a different spec, and one that reports itself clean.
    """

    requirements = payload.get("requirements")
    if not isinstance(requirements, Mapping):
        return {}

    out: dict[str, Any] = {}
    for field in ("specId", "version", "objective", "intent"):
        value = requirements.get(field)
        if not isinstance(value, str) or not value.strip():
            return {}
        out[field] = value

    scope = requirements.get("scope")
    if not isinstance(scope, Sequence) or isinstance(scope, (str, bytes)) or not scope:
        return {}
    if not all(isinstance(item, str) for item in scope):
        return {}
    out["scope"] = list(scope)

    raw_criteria = requirements.get("acceptanceCriteria")
    if raw_criteria is None:
        raw_criteria = requirements.get("acceptance_criteria")
    if raw_criteria is not None:
        if not isinstance(raw_criteria, Sequence) or isinstance(raw_criteria, (str, bytes)):
            return {}
        criteria = [_criterion(item) for item in raw_criteria]
        if any(item is None for item in criteria):
            return {}
        out["acceptanceCriteria"] = criteria

    for v2_name, core_name, required_keys in (
        ("constraints", "constraints", ("key", "value")),
        ("assumptions", "assumptions", ("assumptionId", "statement")),
        ("non_goals", "nonGoals", ()),
        ("nonGoals", "nonGoals", ()),
    ):
        raw = requirements.get(v2_name)
        if raw is None:
            continue
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return {}
        if not required_keys:
            if not all(isinstance(item, str) for item in raw):
                return {}
            out[core_name] = list(raw)
            continue
        for item in raw:
            if not isinstance(item, Mapping) or any(key not in item for key in required_keys):
                return {}
        out[core_name] = [dict(item) for item in raw]

    base = requirements.get("baseSnapshotSha")
    if isinstance(base, str) and base:
        out["baseSnapshotSha"] = base

    snapshot = _taskspec_snapshot(payload.get("repository_snapshot"))
    if snapshot is None:
        return {}

    request: dict[str, Any] = {"requirements": out, "repository_snapshot": snapshot}
    previous = payload.get("previous_task_spec")
    if isinstance(previous, Mapping) and previous:
        request["previous_task_spec"] = dict(previous)
    policy = payload.get("policy_profile")
    if isinstance(policy, Mapping) and policy:
        request["policy_profile"] = dict(policy)
    return request


def _policy_blocked(outputs: Mapping[str, Any]) -> str | None:
    """A policy denial must not read as a validated dispatch.

    The legacy handler returns BLOCKED with ``POLICY_DENIED`` on DENY. The core
    returns the denial as data and SUCCEEDED for the evaluation, which is right
    for the core - it was asked to evaluate a policy and it did. Over the bridge
    that becomes LOCAL_ENGINEERING_VALIDATED for a *denied action*, which is the
    single worst instance of this defect class in the package: a caller gating
    on the dispatch status proceeds with an action policy refused.

    Only DENY blocks, matching legacy. ASK_USER, REQUIRE_ESCALATION and
    REQUIRE_SECOND_REVIEW are held for a human, not refused, and legacy reports
    them through ``approval_request`` rather than the status.
    """

    decision = outputs.get("policy_decision")
    if isinstance(decision, Mapping) and decision.get("decision") == "DENY":
        return "POLICY_DENIED"
    return None


def _compat_blocked(outputs: Mapping[str, Any]) -> str | None:
    """Restore a blocking verdict on a breaking contract change.

    Legacy blocks on breaking-and-unknown-consumers. The core computes
    ``compatibility_report.decision.blocking`` under the policy the *caller*
    named, so this is that policy's own verdict rather than a stricter one the
    bridge invented - a permissive policy yields an empty blocking list and
    nothing is blocked.

    It does block in one case legacy did not: a breaking change with a complete
    consumer inventory. Legacy let that through on the theory that a known
    consumer set can be fixed. The core has already decided under the stated
    policy that the change is blocking, and overriding that decision to match
    the shallower engine would be the bridge overruling a verdict - the thing
    rule 1 exists to forbid, in the direction that ships the break.
    """

    report = outputs.get("compatibility_report")
    if not isinstance(report, Mapping):
        return None
    decision = report.get("decision")
    if isinstance(decision, Mapping) and decision.get("blocking"):
        return "CONTRACT_CHANGE_BLOCKING"
    return None


def _validation_blocked(outputs: Mapping[str, Any]) -> str | None:
    """A plan that dropped a *required* check is not a validated plan.

    Legacy blocks when ``validation_budget.status`` is not VALID. The core makes
    SKIPPED first-class and reports each dropped check with its reason and
    whether it was required - which is strictly better information, and was
    being thrown away at the status line: a budget that trimmed four required
    checks came back LOCAL_ENGINEERING_VALIDATED.

    That is the exact failure the core's SKIPPED modelling exists to prevent
    ("a check that never ran is indistinguishable from one that passed"),
    arriving through the bridge instead of through the engine. Skipping an
    optional check is a legitimate trim and does not block.
    """

    plan = outputs.get("validation_plan")
    if not isinstance(plan, Mapping):
        return None
    skipped = plan.get("skipped")
    if not isinstance(skipped, Sequence) or isinstance(skipped, (str, bytes)):
        return None
    if any(isinstance(item, Mapping) and item.get("required") is True for item in skipped):
        return "VALIDATION_PLAN_INCOMPLETE"
    return None


def _taskspec_blocked(outputs: Mapping[str, Any]) -> str | None:
    """Preserve the legacy BLOCKED verdict for a spec with a blocking question.

    Legacy blocks when any ambiguity is severity HIGH. The core says the same
    thing in the outputs - ``ambiguity_register.blockingQuestionCount`` - and
    returns SUCCEEDED, because it was asked to compile a spec and it compiled
    one. Without this the caller's BLOCKED becomes LOCAL_ENGINEERING_VALIDATED
    purely because a different engine answered, which is a safety signal
    changing meaning behind their back.

    The core blocks strictly more often than legacy, not less: legacy's four
    detectors only fire on a field that is declared and empty, so an untraceable
    criterion or a contradictory constraint passes it silently.
    """

    register = outputs.get("ambiguity_register")
    if not isinstance(register, Mapping):
        return None
    count = register.get("blockingQuestionCount")
    if isinstance(count, int) and not isinstance(count, bool) and count > 0:
        return "AMBIGUITY_BLOCKED"
    return None


def _taskspec_snapshot(snapshot: Any) -> Mapping[str, Any] | None:
    """Present a v2 repository snapshot as the core's ``{snapshotSha, paths}``.

    Unlike the census route, the sha *is* forwarded here. Nothing recomputes it:
    the core stores it on the spec so that a spec compiled against snapshot A
    can be recognised later as not describing snapshot B. It is an identity the
    caller owns, and there is no second identity for it to disagree with.

    ``paths`` comes from the paths the snapshot already lists, which is a
    reading of the caller's own data. A snapshot that lists no paths sets
    ``pathsMeasured: false`` rather than an empty path list, because an empty
    scope diff computed against "we did not look" is a delta that reports no
    scope movement for the wrong reason.
    """

    if not isinstance(snapshot, Mapping):
        return None
    sha = snapshot.get("sha256") or snapshot.get("snapshotSha")
    if not isinstance(sha, str) or not sha:
        return None

    paths: list[str] | None = None
    raw = snapshot.get("paths")
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        if not all(isinstance(item, str) for item in raw):
            return None
        paths = list(raw)
    else:
        files = _inline_files(snapshot)
        if files:
            paths = sorted(files)

    if paths is None:
        return {"snapshotSha": sha, "paths": [], "pathsMeasured": False}
    return {"snapshotSha": sha, "paths": paths, "pathsMeasured": True}


def _taskspec_outputs(payload: Mapping[str, Any],
                      outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Map onto the five declared v2 fields.

    ``specDigest``, ``policyProfile``, ``snapshot`` and ``gates`` have no v2
    field and are folded into ``task_spec`` rather than dropped. ``gates`` is
    the one that matters: ``traceability-complete`` is false whenever a
    criterion has no check reference, and that is the fact v2's shape has no
    room for and legacy has no way to discover.
    """

    spec = dict(outputs.get("task_spec") or {})
    spec["spec_digest"] = outputs.get("specDigest")
    spec["gates"] = outputs.get("gates")
    spec["snapshot"] = outputs.get("snapshot")
    if outputs.get("policyProfile") is not None:
        spec["policy_profile"] = outputs["policyProfile"]
    return {
        "task_spec": spec,
        "spec_delta": outputs.get("spec_delta"),
        "acceptance_criteria": outputs.get("acceptance_criteria"),
        "ambiguity_register": outputs.get("ambiguity_register"),
        "affected_node_set": outputs.get("affected_node_set"),
    }


def _census_request(payload: Mapping[str, Any], context: Any = None) -> Mapping[str, Any]:
    """Promote when the snapshot carries real file text.

    The core reads a repository through a ``RepositoryReader`` port; the v2
    payload carries its files inline, so ``_InlineSnapshotReader`` presents
    exactly those bytes through that interface and invents nothing. A snapshot
    that lists paths without content is left to the legacy engine, which will
    raise on it.

    **``snapshotSha`` is deliberately not forwarded.** The core compares a
    caller-stated sha against the reader's own and raises ``SNAPSHOT_CHANGED``
    on a mismatch, which is a real and valuable guard for a caller holding a
    reader over a live tree. Over this bridge the reader is built *from* the
    payload, and its sha is a digest of the inline bytes under this package's
    scheme - it is not the same number as whatever id the caller's snapshot
    tool assigned, so forwarding the caller's sha would make the guard fire on
    every request that states one. That is the placeholder-pin mistake again: a
    check that always fails is not strict, it is broken. Both identities survive
    in the output instead - see ``_census_outputs``.

    ``failOnPartial`` is likewise not forwarded. v2 callers have no way to ask
    for a raise, and turning their working call into a hard failure is not the
    bridge's decision to make; ``serve`` records ``KERNEL_PARTIAL`` when the
    core reports it.

    Worth stating plainly: over *this* bridge PARTIAL cannot actually arise. The
    core's unmeasured-file handling is one of the real reasons to route here,
    but it triggers on a file the reader cannot read, and a v2 payload that
    carries a file's content has by construction already read it. The guarantee
    is live for a reader over a real tree (the filestore adapter); over an
    inline snapshot it is a guarantee with nothing to catch. Claiming it as a
    win for this route would be counting a property that cannot fire.
    """

    files = _inline_files(payload.get("immutable_repository_snapshot"))
    if not files:
        return {}
    return {"reader": _InlineSnapshotReader(files)}


def _census_outputs(payload: Mapping[str, Any],
                    outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Map onto the six declared v2 fields, keeping both snapshot identities.

    Same rule as the semantic index: the declared ``sha256`` is an id assigned
    by whatever took the snapshot and is what downstream staleness comparisons
    are written against, so it stays as ``snapshot_sha``; the digest the core
    computed over the actual bytes rides beside it as ``content_digest``. Two
    ids that can disagree are worth showing.

    ``censusDigest``, ``definitions`` and ``gates`` have no v2 field. They are
    kept inside ``repository_profile`` rather than dropped: ``definitions`` says
    what each count actually means (which of "lines" includes blank lines, what
    "module" is), and a count whose definition is unstated is a count two
    readers will disagree about while both believing they agree.
    """

    body = dict(outputs.get("repositoryProfile") or {})
    declared = payload.get("immutable_repository_snapshot")
    body["content_digest"] = body.get("snapshotSha")
    if isinstance(declared, Mapping) and isinstance(declared.get("sha256"), str):
        body["snapshot_sha"] = declared["sha256"]
    else:
        body["snapshot_sha"] = body.get("snapshotSha")
    body["census_digest"] = outputs.get("censusDigest")
    body["definitions"] = outputs.get("definitions")
    body["gates"] = outputs.get("gates")

    return {
        "repository_profile": body,
        "module_graph": outputs.get("moduleGraph"),
        "build_graph": outputs.get("buildGraph"),
        "entrypoint_map": outputs.get("entrypointMap"),
        "data_flow_map": outputs.get("dataFlowMap"),
        "risk_map": outputs.get("riskMap"),
    }


def _semantic_index_request(payload: Mapping[str, Any],
                            context: Any = None) -> Mapping[str, Any]:
    """Promote when the snapshot carries real file text; refuse to guess otherwise.

    A snapshot that lists paths without content cannot be indexed by anything -
    the legacy engine "handles" it by emitting an index with no symbols, which
    reads as "this repository has no functions in it". The kernel is given the
    text or it is not asked.

    ``changedPaths`` is forwarded only when the caller states a change set,
    because an incremental update over an invented change set is a full rebuild
    wearing the word "incremental".
    """

    files = _inline_files(payload.get("repository_snapshot"))
    if files is None:
        return {}

    request: dict[str, Any] = {"reader": _InlineSnapshotReader(files)}

    prior = payload.get("previous_index")
    changed = payload.get("change_set")
    changed_paths: list[str] = []
    if isinstance(changed, Mapping):
        raw = changed.get("paths")
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            changed_paths = [item for item in raw if isinstance(item, str)]
    elif isinstance(changed, Sequence) and not isinstance(changed, (str, bytes)):
        for item in changed:
            if isinstance(item, str):
                changed_paths.append(item)
            elif isinstance(item, Mapping) and isinstance(item.get("path"), str):
                changed_paths.append(item["path"])

    # An incremental update needs BOTH halves, and it needs the prior index as a
    # live object: the core rejects a JSON payload here on purpose, because it
    # cannot verify that a hand-assembled index is one it produced, and an
    # incremental update against a forged prior is worse than a full rebuild.
    #
    # So incremental is only reachable in-process, from a caller holding the
    # Index. Over this JSON dispatcher it is not expressible at all, and the
    # request stays a full build rather than pretending otherwise. That is a
    # real limitation of the core over this boundary, recorded in
    # docs/MERGE_DECISIONS.md rather than hidden behind a silent downgrade.
    if changed_paths and not isinstance(prior, Mapping) and prior is not None:
        request["priorIndex"] = prior
        request["changedPaths"] = sorted(set(changed_paths))
    return request



def _semantic_index_outputs(payload: Mapping[str, Any],
                            outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Map onto the six declared v2 fields, keeping BOTH snapshot identities.

    The v2 ``repository_snapshot.sha256`` is an id assigned by whatever took the
    snapshot; it is not required to be a digest of the content, and this adapter
    has no business redefining that. So the declared id is what the index
    reports as ``snapshot_sha`` - a consumer's staleness comparison keeps
    working - and the digest the core computed over the actual bytes is carried
    beside it as ``content_digest``. Two ids that can disagree are worth showing;
    silently replacing one with the other is how a consumer ends up comparing
    against a number that means something else.
    """

    index = dict(outputs.get("semanticIndex") or outputs.get("index") or {})
    declared = payload.get("repository_snapshot")
    index["content_digest"] = index.get("repoSnapshotSha")
    if isinstance(declared, Mapping) and isinstance(declared.get("sha256"), str):
        index["snapshot_sha"] = declared["sha256"]
    else:
        index["snapshot_sha"] = index.get("repoSnapshotSha")

    impact = outputs.get("testImpactMap") or {}
    invalidation = impact.get("invalidationSet") if isinstance(impact, Mapping) else None
    return {
        "semantic_index": index,
        "symbol_graph": outputs.get("symbolGraph"),
        "call_graph": outputs.get("callGraph"),
        "dependency_graph": outputs.get("dependencyGraph"),
        "test_impact_map": impact,
        "invalidation_set": invalidation if invalidation is not None else [],
    }



_DECL_SHAPE = frozenset({"name", "kind"})
_CHECK_SHAPE = frozenset({"checkId"})


def _declaration_list(value: Any) -> list[Mapping[str, Any]] | None:
    """Return ``value`` if it is already a list of API declarations."""

    if isinstance(value, Mapping) or not isinstance(value, Sequence):
        return None
    if isinstance(value, (str, bytes)):
        return None
    items = [item for item in value if isinstance(item, Mapping)]
    if len(items) != len(value):
        return None
    # An EMPTY list is a valid surface, not a missing one: "everything was
    # removed" is exactly the change this engine most needs to be able to see,
    # and rejecting it would send the most breaking diff there is to the engine
    # that cannot reason about it.
    if not all(_DECL_SHAPE <= set(item) for item in items):
        return None
    return items


def _compat_request(payload: Mapping[str, Any], context: Any = None) -> Mapping[str, Any]:
    """Promote only when the contracts are declared surfaces, not arbitrary documents.

    The legacy engine diffs two dictionaries structurally: any changed value is
    ``breaking: True``. That is fail-closed, which is the right default, but it
    cannot tell a widened parameter type from a narrowed one, and those have
    opposite compatibility meanings - narrowing a parameter breaks callers,
    widening it does not, and the reverse holds for return types. The core can,
    because it is given declarations with names, kinds, parameters and types.

    A payload whose contracts are free-form documents is left to the legacy
    engine rather than being coerced into declarations: inferring that some key
    is "really" a parameter list would put variance reasoning on top of a guess,
    which is worse than an honest structural diff.
    """

    baseline = _declaration_list(payload.get("baseline_contracts"))
    candidate = _declaration_list(payload.get("candidate_contracts"))
    if baseline is None or candidate is None:
        return {}
    if not baseline and not candidate:
        # Two empty surfaces carry no contract at all; there is nothing to
        # compare and saying "compatible" would be an answer about nothing.
        return {}

    # The core takes a *surface* - {"declarations": [...]} - not a bare list. The
    # v2 field carries the declarations directly, so wrapping them is a shape
    # translation over the caller's own data, nothing more.
    request: dict[str, Any] = {
        "baselineSurface": {"declarations": baseline},
        "candidateSurface": {"declarations": candidate},
    }
    # The core refuses an empty policy - "an empty policy is a deny" - and it is
    # right: strict, deprecate-first and best-effort give different verdicts on
    # the same diff, so choosing one on the caller's behalf would be answering a
    # question they did not ask. No policy, no promotion.
    #
    # The core takes the policy as a NAME (strict / deprecate-first /
    # best-effort), not a settings object. A v2 caller may send either, so a
    # mapping is accepted when it names the policy in a field; a mapping full of
    # unrelated settings is not translated, because picking one of its keys to
    # mean "the policy" would be a guess.
    policy = payload.get("compatibility_policy")
    named: str | None = None
    if isinstance(policy, str) and policy.strip():
        named = policy
    elif isinstance(policy, Mapping):
        for key in ("publicApiPolicy", "policy", "mode", "name"):
            value = policy.get(key)
            if isinstance(value, str) and value.strip():
                named = value
                break
    if named is None:
        return {}
    request["policy"] = named

    # The core wants {"consumers": [...], "complete": bool}. `complete` says
    # whether the caller believes it knows ALL consumers, and it decides whether
    # an unreferenced removal can be called safe - so it is never defaulted to
    # true here. A bare v2 list means "these consumers, completeness unstated".
    consumers = payload.get("consumer_inventory")
    if isinstance(consumers, Mapping):
        request["consumerInventory"] = dict(consumers)
    elif isinstance(consumers, Sequence) and not isinstance(consumers, (str, bytes)):
        request["consumerInventory"] = {"consumers": list(consumers), "complete": False}
    for wire_key, field in (("baseline_wire", "baselineWire"),
                            ("candidate_wire", "candidateWire")):
        wire = payload.get(wire_key)
        if isinstance(wire, Sequence) and not isinstance(wire, (str, bytes)):
            request[field] = {"messages": list(wire)}
    return request


def _compat_outputs(payload: Mapping[str, Any],
                    outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Map onto the five declared v2 fields.

    ``adapter_plan`` has no counterpart in the core, which produces a decision
    and a deprecation path rather than a patch outline. Rather than omit the
    field or invent adapter steps, it is restated from the breaking changes the
    core already computed and labelled as derived, so a reader can see it is a
    view of that list and not an independent piece of analysis.
    """

    breaking = list(outputs.get("breakingChanges") or ())
    report = dict(outputs.get("compatibilityReport") or {})
    report["decision"] = outputs.get("compatibilityDecision")
    return {
        "compatibility_report": report,
        "breaking_changes": breaking,
        "adapter_plan": {
            "required": bool(breaking),
            "derivedFrom": "breakingChanges",
            "steps": [f"adapt {item.get('member', item.get('path', 'unknown'))}"
                      for item in breaking],
        },
        "migration_plan": outputs.get("migrationPlan"),
        "rollback_contract": outputs.get("rollbackContract"),
    }


def _validation_request(payload: Mapping[str, Any], context: Any = None) -> Mapping[str, Any]:
    """Promote when the test catalogue declares checks with their dependencies.

    The legacy planner chains gates in a line - each criterion depends on the
    previous one purely because of its position in the list - so it cannot say
    what may run in parallel, and it has no notion of a check being skipped.
    The core builds a DAG from declared dependencies and treats SKIPPED as a
    first-class status distinct from PASSED and from NOT_RUN, which is the
    property that stops a budget-trimmed run from reading as a clean one.

    Dependencies are never inferred from list order here. A catalogue that does
    not declare them stays with the legacy engine, because inventing an edge
    would produce a DAG that describes this adapter's guess rather than the
    caller's test suite.
    """

    catalogue = payload.get("test_catalog")
    if isinstance(catalogue, Mapping) or not isinstance(catalogue, Sequence):
        return {}
    if isinstance(catalogue, (str, bytes)):
        return {}
    checks = [item for item in catalogue if isinstance(item, Mapping)]
    if not checks or len(checks) != len(catalogue):
        return {}
    if not all(_CHECK_SHAPE <= set(item) for item in checks):
        return {}

    # The core refuses an absent budget - "an absent budget is not an unlimited
    # budget" - and it is right: a plan with no ceiling cannot report anything as
    # trimmed, so every check reads as selected. Supplying a default here would
    # invent the one number the caller is supposed to own, so a payload with no
    # budget stays with the legacy planner.
    budget = payload.get("validation_budget")
    if not isinstance(budget, Mapping) or not budget:
        return {}

    request: dict[str, Any] = {"checks": checks, "budget": dict(budget)}
    spec = payload.get("task_spec")
    if isinstance(spec, Mapping):
        criteria = spec.get("acceptance_criteria", spec.get("acceptance"))
        if isinstance(criteria, Sequence) and not isinstance(criteria, (str, bytes)):
            shaped = [item for item in criteria if isinstance(item, Mapping)]
            if shaped and len(shaped) == len(criteria):
                request["criteria"] = shaped
    outcomes = payload.get("recorded_outcomes")
    if isinstance(outcomes, Mapping) and outcomes:
        request["recordedOutcomes"] = dict(outcomes)
    return request


def _validation_outputs(payload: Mapping[str, Any],
                        outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """One-to-one onto the five declared v2 fields.

    The core's extra products - the executed result and the negative-coverage
    check list - ride inside ``validation_plan`` rather than being dropped: a
    plan whose execution outcome is invisible is the thing that lets a skipped
    required check read as a passed one.
    """

    plan = dict(outputs.get("validationPlan") or {})
    if outputs.get("validationResult") is not None:
        plan["validationResult"] = outputs["validationResult"]
    if outputs.get("negativeChecks") is not None:
        plan["negativeChecks"] = outputs["negativeChecks"]
    plan["executed"] = outputs.get("executed")
    return {
        "validation_plan": plan,
        "validation_dag": outputs.get("validationDag"),
        "critical_path": outputs.get("criticalPath"),
        "coverage_map": outputs.get("coverageMap"),
        "validation_budget": outputs.get("validationBudget"),
    }



#: v2 declares seven key parts; the core requires nine. The two extra are the
#: ones a caller must state, never a bridge - see ``_cache_request``.
_V2_KEY_PARTS: Mapping[str, str] = {
    "snapshot_hash": "repoSnapshotSha",
    "task_spec_hash": "taskSpecHash",
    "workflow_version": "workflowVersion",
    "skill_versions": "skillVersions",
    "policy_hash": "policyHash",
    "tool_schema_versions": "toolSchemaVersions",
    "model_profile": "modelProfile",
}
_EXTRA_KEY_PARTS: Mapping[str, str] = {
    "prompt_prefix_digest": "promptPrefixDigest",
    "environment_fingerprint": "environmentFingerprint",
}


def _cache_request(payload: Mapping[str, Any], context: Any = None) -> Mapping[str, Any]:
    """Promote only a caller who is unambiguously asking for the new fabric.

    **What the legacy engine actually is.** It is a working cache, not a stub:
    it hashes the seven key parts v2 declares, reads the tenant-scoped cache
    table, and writes through it when the payload carries a ``value``. Callers
    depend on it. Two things are wrong with it, and both are silent:

    * its key omits the prompt prefix digest and the environment fingerprint, so
      two computations that differ only in prompt prefix or environment collide
      on one key and each serves the other's result;
    * a read returns whatever sits at the digest. Nothing re-checks that the
      stored entry was produced under the parts being requested, so a collision
      or a drifted index is indistinguishable from a hit.

    The core fixes both - nine-part keys, and a stored entry is re-verified
    against the requested key before it is served - but the fix is not free: two
    of its nine parts are ones v2 never declared, and neither is derivable from
    the other seven. Filling either with a plausible constant would make
    genuinely different computations share a key, which is the exact failure the
    core exists to remove, arriving silently.

    So promotion needs the caller to have said enough to be unambiguous:

    1. **All nine key parts.** Seven means the caller is speaking v2, and v2's
       cache is correct for v2's key. They keep it, and the gap is recorded.
    2. **A non-empty ``layer_config``.** It names the tenant and the cache
       class. A default tenant would let one tenant read another's entries; a
       default cache class would let a result claim reuse it was never certified
       for - a secret-bound value cached as if it were deterministic. Both are
       part of the key, so neither gets a default here.
    3. **No bare ``value``.** ``value`` is the v2 store-through field; the core
       admits through ``candidate``, which additionally carries determinism and
       measured compute cost. Translating ``value`` into a candidate means
       inventing both: ``deterministic`` would default to true for a result
       nobody called deterministic, and an unmeasured cost is refused, so the
       caller's working write would turn into a stated refusal. Downgrading a
       caller's working cache into an explained non-cache is still downgrading
       it. A ``value`` payload stays on legacy; a caller who wants admission
       sends ``candidate`` and states what they measured.
    4. **A live store and tenant on the context.** The core fails closed with
       ``CACHE_UNCONFIGURED`` when no fabric is bound, and that is right for the
       core - "no cache is configured" and "the cache missed" are different
       facts. But over the bridge it would turn a dispatch that merely lacks a
       store into a hard failure of a skill the legacy engine could have served.
       So the absence of a store decides the *route*, before the call, rather
       than surfacing as an error after it.
    """

    if payload.get("value") is not None or "value" in payload:
        return {}
    if getattr(context, "store", None) is None:
        return {}
    if not str(getattr(context, "tenant_id", "") or ""):
        return {}

    parts: dict[str, Any] = {}
    for v2_name, core_name in _V2_KEY_PARTS.items():
        value = payload.get(v2_name)
        if value is None:
            return {}
        parts[core_name] = value
    for v2_name, core_name in _EXTRA_KEY_PARTS.items():
        value = payload.get(v2_name)
        if value is None:
            return {}
        parts[core_name] = value

    config = payload.get("layer_config")
    if not isinstance(config, Mapping) or not config:
        return {}

    request: dict[str, Any] = {"cache_key_inputs": parts, "layer_config": dict(config)}
    for optional in ("operation", "candidate", "invalidate"):
        value = payload.get(optional)
        if value is not None:
            request[optional] = value
    return request


def _cache_outputs(payload: Mapping[str, Any],
                   outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    """Map onto the six declared v2 fields.

    The lookup result and the admission decision have no v2 field, and they are
    the two things that say *why* this call hit, missed or refused to store. They
    ride inside ``hit_miss`` rather than being dropped, because a hit with no
    stated reason is exactly the thing a reviewer cannot check.

    Two fields the core does not emit are added, and both exist for the same
    reason: a per-call fabric reports numbers whose shape invites a reading they
    do not support.

    ``provenance.freshnessPin``.
    The core reports what the fabric is pinned to, which reads as an
    independent statement about the live tree; over this bridge the pin is
    derived from the request itself (see ``_durable_cache_fabric``), so the same
    two hashes appear on both sides of a comparison that can no longer fail.
    Reporting the pin without saying where it came from would let a reviewer
    read agreement as verification. This field says which one it is.

    ``cache_metrics.scope``. The fabric lives for one dispatch, so its counters
    are this call's, not the deployment's - a single hit reads as a hit rate of
    1000 per mille and a single miss as 0. Those are the only two values the
    field can take here, which makes it useless as a health signal and
    dangerous as a reported one. Saying the scope out loud is cheaper than
    hoping nobody graphs it.
    """

    hit_miss = dict(outputs.get("hit_miss") or {})
    if outputs.get("lookup_result") is not None:
        hit_miss["lookupResult"] = outputs["lookup_result"]
    if outputs.get("admission_decision") is not None:
        hit_miss["admissionDecision"] = outputs["admission_decision"]

    provenance = outputs.get("provenance")
    if isinstance(provenance, Mapping):
        provenance = dict(provenance) | {
            "freshnessPin": "request-derived",
            "freshnessPinNote": (
                "snapshot and policy are taken from the request's own key parts; "
                "STALE_SNAPSHOT and STALE_POLICY_SNAPSHOT cannot fire over this "
                "bridge. Both remain part of the cache key, so an entry from "
                "another snapshot or policy is never a hit candidate."
            ),
        }

    metrics = outputs.get("cache_metrics")
    if isinstance(metrics, Mapping):
        metrics = dict(metrics) | {
            "scope": "single-call",
            "scopeNote": (
                "the fabric is constructed and discarded inside one dispatch, so "
                "these counters describe this call only. hitRatePerMille is 0 or "
                "1000 by construction and is not a deployment hit rate; aggregate "
                "across calls to get one."
            ),
        }

    return {
        "cache_key": outputs.get("cache_key"),
        "cache_entry": outputs.get("cache_entry"),
        "hit_miss": hit_miss,
        "invalidation_set": outputs.get("invalidation_set"),
        "provenance": provenance,
        "cache_metrics": metrics,
    }



@contextmanager
def _durable_cache_fabric(context: Any, request: Mapping[str, Any]) -> Iterator[None]:
    """Bind a durable, tenant-scoped cache fabric around the call.

    The core fails closed with ``CACHE_UNCONFIGURED`` when no fabric is bound,
    and that is the right default - "no cache is configured" and "the cache
    missed" are different facts, and degrading one into the other would let an
    unconfigured deployment report a healthy miss rate forever.

    Binding here gives the skill an L2 over ``DurableStore``'s tenant-scoped
    cache table, so an entry outlives the request and one tenant cannot read
    another's.

    **The tenant comes from the context; the snapshot and policy come from the
    request.  That split is deliberate and the two halves are not symmetric.**

    Tenancy is an *isolation boundary*, so it must not be chosen by the data
    being isolated: the payload's ``layer_config.tenantId`` is caller-supplied,
    and letting supplied data pick the boundary is how cross-tenant reads
    happen.  The context's tenant is the one the dispatcher authenticated.  When
    the two disagree the core raises ``ISOLATION_VIOLATION`` and the call fails
    - that is the check working, not a mapping bug to smooth over.

    The snapshot and policy are a *freshness pin*, and a pin needs a fact this
    bridge does not have.  In a long-lived server the fabric is constructed once
    against the tree the process is serving, so ``STALE_SNAPSHOT`` catches a
    caller asking about a tree that has moved on.  Here the fabric is built and
    discarded inside one dispatch, and ``DispatchContext`` carries no snapshot
    identity, so there is no independent "live tree" to pin against.  Pinning to
    a placeholder - which is what this did first - does not preserve the guard;
    it makes the guard fire on *every* call, so the fabric rejects every key it
    is ever handed and the skill can never hit.  A check that refuses everything
    is not a strict check, it is a broken one.

    So the pin is derived from the key parts the request already states, and the
    honest consequence is written into the response: ``provenance.freshnessPin``
    reports ``"request-derived"``, meaning ``STALE_SNAPSHOT`` and
    ``STALE_POLICY_SNAPSHOT`` cannot fire over this bridge.  What is *not* given
    up is the thing the skill exists for: the snapshot and the policy remain two
    of the nine parts of the key, so an entry produced under a different
    snapshot has a different fingerprint and is never a hit candidate at all.
    The guarantee that a hit is provably the same inputs is intact; the
    guarantee that those inputs describe the current tree is the caller's, and
    the response now says so rather than implying otherwise.
    """

    store = getattr(context, "store", None)
    tenant = str(getattr(context, "tenant_id", "") or "")
    if store is None or not tenant:
        yield
        return

    parts = request.get("cache_key_inputs")
    if not isinstance(parts, Mapping):
        yield
        return
    snapshot = parts.get("repoSnapshotSha")
    policy = parts.get("policyHash")
    if not isinstance(snapshot, str) or not isinstance(policy, str):
        # ``_cache_request`` refuses to promote without both, so this is
        # unreachable from the routing table.  It stays because binding a
        # fabric to a guessed identity is the one failure mode this whole
        # function exists to avoid, and leaving no fabric bound makes the core
        # say ``CACHE_UNCONFIGURED`` - which is true and checkable.
        yield
        return

    from elmos_autonomy_kernel.cache import (
        AdmissionPolicy,
        CacheFabric,
        KeyValueLayer,
        bind_fabric,
        bound_fabric,
    )

    from .kernel_store_adapter import DurableStoreKeyValueStore

    try:
        previous: Any = bound_fabric()
    except CoreKernelError:
        previous = None

    fabric = CacheFabric(
        tenant_id=tenant,
        snapshot_sha=snapshot,
        policy_hash=policy,
        layers=[KeyValueLayer(DurableStoreKeyValueStore(store, tenant_id=tenant))],
        policy=AdmissionPolicy(cacheable_classes=_BRIDGE_CACHEABLE_CLASSES),
        clock=_SystemClock(),
    )
    bind_fabric(fabric)
    try:
        yield
    finally:
        # Restored on the exception path too - a leaked fabric would leave one
        # tenant's cache installed as the process default, which is precisely
        # what this function is here to prevent.
        bind_fabric(previous)


def _bridge_cacheable_classes() -> Any:
    """Which reuse classes this bridge is willing to cache, and why only these.

    ``AdmissionPolicy`` defaults to the empty set, which denies every admission.
    That is the correct default for the core - a fabric that was never told what
    it may cache must not decide for itself - but binding it here would give the
    skill a fabric that reports ``CLASS_NOT_CACHEABLE`` on every call. A policy
    that refuses everything is not a strict policy, it is a cache that does not
    work while looking like one, and its zero hit rate reads as a workload
    property rather than a configuration mistake. So the bridge states a set and
    owns it; ``provenance.admissionPolicy`` reports it on every response.

    ``deterministic`` and ``environment-bound`` are in. Both are fully described
    by the key: the nine parts include the environment fingerprint, so an
    environment-bound result is only ever served back into the environment it
    was produced in.

    ``semantic`` and ``time-bound`` are out, and their exclusion is the reason
    this is a real decision rather than a formality. A semantic entry claims
    reuse across inputs judged *similar*, and the key cannot express that
    judgement, so the fabric would be trusting an equivalence it never checked.
    A time-bound entry's correctness depends on wall-clock freshness, which no
    part of the key captures; a TTL bounds how stale it gets, it does not make a
    stale answer wrong-looking. A caller naming either gets a bypass with
    ``CLASS_NOT_CACHEABLE`` stated in the response - which is this check being
    reachable, not decorative.

    ``secret-bound`` is not listed because the core refuses it in
    ``AdmissionPolicy.__post_init__`` regardless; naming it here would raise.
    """

    from elmos_autonomy_kernel.cache import CacheClass

    return frozenset({CacheClass.DETERMINISTIC, CacheClass.ENVIRONMENT_BOUND})


#: Resolved once at import; see ``_bridge_cacheable_classes`` for the reasoning.
_BRIDGE_CACHEABLE_CLASSES = _bridge_cacheable_classes()


class _SystemClock:
    """Real time for the durable fabric; the core injects its clock everywhere."""

    def now(self):
        from datetime import UTC, datetime
        return datetime.now(tz=UTC)

    def monotonic_ns(self) -> int:
        import time
        return time.monotonic_ns()



# --- the routing table -------------------------------------------------------
#
# Every row here was decided by reading both implementations, not by comparing
# line counts.  The rationale states what the legacy implementation actually
# does, because that is the claim a reviewer should attack first.

_ROWS: tuple[BridgeSpec, ...] = (
    _spec(
        "repository-model-elo",
        build_request=_elo_request,
        rationale="legacy computes 1000 + (win_rate - 0.5) * 400 in floating point: a "
        "win-rate rescale, not a rating system. No pairwise updates, no K "
        "factor, no order sensitivity, so two contestants who never met can be "
        "ranked against each other. The kernel keeps integer centi-ratings, "
        "reports provisional ratings separately, and publishes the measured "
        "order tolerance instead of pretending Elo is order-independent.",
    ),
    _spec(
        "agent-arena",
        build_request=_arena_request,
        rationale="legacy reads each contestant's own declared `quality` field as its "
        "score - nothing is executed or graded, and there is no isolation "
        "between contestant and grader. The kernel separates TaskView from "
        "TaskSecret structurally, runs four anti-cheat detectors, and "
        "quarantines rather than silently drops a flagged match.",
    ),
    _spec(
        "durable-run-orchestrator",
        build_request_with_context=_orchestrator_request,
        persist_outputs=_persist_durable_run,
        rationale="both are real, and this is the one row where the legacy side owns "
        "something the kernel does not. The kernel adds the 19-state "
        "transition table, hash-chained replay, unresolved side-effect "
        "reconciliation and the requirement-update rerun set, but its registry "
        "entry point is pure - it drives an in-memory log on a fixed clock. The "
        "legacy handler's DurableStore rows are the thing worth keeping, so the "
        "row delegates the decision and then writes the kernel's chained events, "
        "state trajectory and checkpoint back through the store-backed ports "
        "adapter. Bridging without that hook would have traded persistence for "
        "depth, which is not a merge.",
    ),
    _spec(
        "execution-authority-kernel",
        build_request_with_context=_authority_request,
        publish_context=_publish_authority,
        rationale="legacy validates an authority mapping; the kernel mints it, refuses a "
        "conversation-scoped subject outright, and can only narrow an authority "
        "- privilege escalation is impossible to express, not merely rejected. "
        "The adapter only promotes a payload whose environment states its own "
        "ceiling (grantedTools, ttlSeconds); without those the narrowing check "
        "would be comparing the request to itself, so such a payload stays with "
        "the legacy engine.",
    ),
    _spec(
        "policy-hook-kernel",
        build_request_with_context=_policy_request,
        persist_outputs=_persist_policy_decision,
        blocked_when=_policy_blocked,
        rationale="both implement deny precedence. The kernel additionally fails closed "
        "on an empty rule set, carries obligations through aggregation, and "
        "rejects a decision taken against a policy snapshot the caller did not "
        "declare - which is why the adapter refuses to supply that declaration "
        "itself.",
    ),
    _spec(
        "workspace-lease-fencing",
        build_request_with_context=_lease_request,
        rationale="the legacy handler acquires a lease and returns it: it never refuses a "
        "second live owner, never re-validates before a write, and has no "
        "takeover record or recovery plan. The kernel adds last-moment "
        "revalidation, an explained takeover and a recovery plan that refuses to "
        "replay a side effect of unknown status. Monotonicity across release is "
        "the one guarantee both sides already have - DurableStore mints "
        "MAX(fencing_token)+1 over released rows too - but nothing enforces it, "
        "so the ports adapter keeps its own high-water mark rather than trusting "
        "a table property a retention job could remove.",
    ),
    _spec(
        "artifact-evidence-protocol",
        build_request=_artifact_request,
        bind_stores=_durable_artifact_store,
        rationale="the kernel binds evidence to the exact input digests it was produced "
        "from, so evidence for snapshot A cannot justify a claim about "
        "snapshot B, and models NOT_RUN as UNSUPPORTED rather than as absence.",
    ),
    _spec(
        "evidence-release-gate",
        map_outputs=_release_gate_outputs,
        build_request=_release_gate_request,
        rationale="the kernel treats NOT_RUN and SKIPPED as blocking, requires a complete "
        "rollback plan, and expires waivers; the legacy gate keys off the "
        "presence of results.",
    ),
    _spec(
        "independent-verification-mesh",
        build_request=_verification_mesh_request,
        rationale="the kernel enforces verifier independence structurally, preserves "
        "dissent instead of averaging it, and refuses to let evidence-free "
        "verdicts carry a quorum.",
    ),
    _spec(
        "cost-eta-observability",
        build_request=_cost_eta_request,
        rationale="the kernel keeps machine wall-clock, human-equivalent effort and HITL "
        "wait in three types that cannot be summed, and reports an unmeasured "
        "component as unmeasured rather than as zero - the defect class this "
        "repository has shipped three times.",
    ),
    _spec(
        "repository-gym-golden-routes",
        build_request=_gym_request,
        rationale="legacy emits every run as NOT_RUN with 'native runner not supplied'. "
        "The kernel freezes the acceptance digest at registration and refuses "
        "to score a run whose acceptance moved.",
    ),
    _spec(
        "task-spec-delta-compiler",
        build_request=_taskspec_request,
        map_outputs=_taskspec_outputs,
        blocked_when=_taskspec_blocked,
        rationale="the delta compiler computes no delta. Legacy's `changed_fields` is a "
        "literal constant - if the previous spec's hash differs at all it returns "
        "['objective', 'acceptance_criteria', 'constraints', 'deliverables'], those "
        "four every time, whatever actually moved - and `cache_invalidation` is that "
        "same list while `affected_nodes` is every criterion, so editing one word of "
        "the objective invalidates everything. The core diffs the two specs and "
        "reports criteria added, removed and changed, scope paths entered and left, "
        "and the steps those actually invalidate. Its ambiguity register is also four "
        "hardcoded field names tested for emptiness, so `scope: []` is HIGH while an "
        "absent scope key is clean, and a requirements object with no acceptance "
        "criteria is given a fabricated one that then reports as satisfied. Promotion "
        "is narrow on purpose: specId, version, objective, intent and a non-empty "
        "scope must all be stated, because minting an id from the objective is the "
        "legacy id scheme and setting intent to the objective hands every ambiguity "
        "detector the one string already known to be well-formed.",
    ),
    _spec(
        "repository-census",
        build_request=_census_request,
        map_outputs=_census_outputs,
        rationale="two defects that fire on this route, and one that does not. "
        "The one that does not, stated first so it is not counted as a win: the "
        "core's unmeasured-file handling - an unreadable file goes into `unmeasured` "
        "and drags the census to PARTIAL, because zero lines is a legal measurement "
        "and 'we could not look' is not - cannot trigger over an inline v2 snapshot, "
        "whose files were readable by construction. It is live for a reader over a "
        "real tree, not here. What does fire: legacy's risk surface substring-matches "
        "file *content* for 'password', 'secret', 'apikey', so a test fixture or a "
        "doc that mentions the word becomes a P1 secret-surface finding (verified: a "
        "test file whose body contains the word is reported P1 secret-surface); the "
        "core computes the risk surface from path shape only and never puts a byte of "
        "file body into an output. And legacy's `module_graph` has nodes and `edges: []` "
        "unconditionally - it is a node list called a graph - and its modules are the "
        "first path segment of every file, so a root-level README is a module. The "
        "core also reports language twice (by extension and by in-file marker) with "
        "an explicit unknown bucket in both, rather than folding a disagreement into "
        "one plausible number, and ships the definitions of its own counts.",
    ),
    _spec(
        "layered-cache-fabric",
        build_request_with_context=_cache_request,
        bind_stores=_durable_cache_fabric,
        map_outputs=_cache_outputs,
        rationale="legacy has a real durable cache - it hashes the seven declared key "
        "parts and reads and writes the tenant-scoped cache table - so this is not a "
        "cache replacing a stub. Two things separate it from the core. Its key omits "
        "the prompt prefix digest and the environment fingerprint, so two computations "
        "that differ only in prompt prefix or environment share a key; and it never "
        "re-checks a hit, so whatever sits at the digest is returned as the answer. "
        "The core keys on all nine parts and re-verifies that the stored entry carries "
        "the requested parts before serving it, which is the guarantee the whole skill "
        "exists for. It also classifies reuse (a secret-bound result is never served) "
        "and states why a candidate was or was not admitted. A caller who states only "
        "the seven parts, or who stores through the v2 `value` field, keeps the legacy "
        "cache exactly as it was - see `_cache_request`. "
        "SCOPE OF THIS CLAIM: it compares the core against the v2 handler and nothing "
        "else. `engines/build-cache-engine` in this same repository keys on 17 "
        "dimensions - the prompt-prefix digest and environment fingerprint argued for "
        "here are both already in it - audits undeclared environment reads as a "
        "hermeticity bug, refuses secret-looking values into a key, and prices "
        "admission against restore cost and tenant quota. Against that, this row is "
        "the shallower implementation. See docs/EXISTING_CAPABILITY_OVERLAP.md.",
    ),
    _spec(
        "contract-compatibility-engine",
        build_request=_compat_request,
        map_outputs=_compat_outputs,
        blocked_when=_compat_blocked,
        rationale="legacy is a generic recursive dict diff: every changed value is "
        "breaking: True. Fail-closed is the right default, but it cannot distinguish a "
        "widened parameter type from a narrowed one, and those mean opposite things - "
        "narrowing a parameter breaks callers, widening it does not, and the reverse "
        "holds for return types. It also has no notion of a wire tag, so retiring a "
        "field number and reusing it later - which silently corrupts data in "
        "production and is invisible to a source-level diff - is not something it can "
        "see. "
        "SCOPE OF THIS CLAIM: it compares the core against the v2 handler and nothing "
        "else. `packages/repository-refactoring/apicompat.py` in this same repository "
        "already separates source-break, binary-break, wire-break and behavior-risk "
        "against this row's BREAKING/RISKY, and does know wire tags - so wire-tag "
        "awareness is an advantage over the legacy handler, not over the repository. "
        "See docs/EXISTING_CAPABILITY_OVERLAP.md.",
    ),
    _spec(
        "validation-dag",
        build_request=_validation_request,
        map_outputs=_validation_outputs,
        blocked_when=_validation_blocked,
        rationale="legacy chains gates in a line: criterion N depends on criterion N-1 "
        "purely because of its position in the list, so the 'DAG' describes the order "
        "the caller happened to write things in rather than what actually depends on "
        "what, and nothing may run in parallel. It also has no SKIPPED status, so a "
        "check that never ran is indistinguishable from one that passed - which is how "
        "a budget-trimmed run reads as a clean one. The core builds the graph from "
        "declared dependencies and makes SKIPPED first-class.",
    ),
    _spec(
        "incremental-semantic-index",
        build_request=_semantic_index_request,
        map_outputs=_semantic_index_outputs,
        rationale="legacy accepts previous_index and never reads it, so every call is a "
        "full rebuild advertised as incremental. Its symbols come from five line "
        "regexes applied to every language regardless of syntax, and it emits a call "
        "edge whenever a known name appears followed by an open paren anywhere in the "
        "file - which produces edges between functions that never call each other. The "
        "kernel parses Python with ast, keeps bounded extractors for the languages it "
        "does not parse and says which is which, omits low-confidence edges rather "
        "than guessing them, and holds itself to incremental-equals-full by digest.",
    ),
    _spec(
        "changegraph-vcs",
        build_request=_changegraph_request,
        map_outputs=_changegraph_outputs,
        rationale="legacy hardcodes \"acyclic\": True. There is no cycle detection at "
        "all, and no region-overlap or entity-level conflict detection either, so a "
        "graph that cannot be applied in any order still reports itself as a DAG and "
        "two changes rewriting the same lines merge silently. The kernel builds the "
        "order, reports a real cycle as a strongly connected component with a witness "
        "path (naming only the changes actually in the cycle, not everything the cycle "
        "blocks), and returns overlapping regions as a conflict the caller must "
        "resolve rather than merging them.",
    ),
    _spec(
        "session-time-travel",
        rationale="legacy returns forked_run={'status': 'PLANNED'} with a fresh uuid4 - "
        "nothing forks, nothing replays, and two identical calls disagree because the "
        "run id is non-deterministic. The kernel actually forks: it copies the prefix "
        "verbatim into a new stream, records a FORK event naming the parent and "
        "sequence, and leaves the parent timeline byte-identical. It also refuses to "
        "fork from inside an unresolved side-effect intent without an explicit "
        "acknowledgement, because that fork would duplicate a real-world effect. No "
        "adapter is needed: the kernel accepts the five declared v2 inputs as they are "
        "and defaults target_point to 'restore at the head of the stream', which is "
        "the only reading of a payload that supplies a stream and no target.",
    ),
    _spec(
        "demonstration-to-skill",
        build_request=_demonstration_request,
        rationale="the kernel requires a counterexample before a draft can leave draft "
        "tier - a rule learned only from positives has no boundary - and "
        "cannot auto-promote.",
    ),
    _spec(
        "auto-improvement-inbox-and-skill-curator",
        build_request=_curator_request,
        rationale="order-independence is NOT the difference - the legacy engine groups on "
        "an exact code/category key, which cannot depend on ingest order either, "
        "and a test now pins that. The kernel's actual advantage is "
        "similarity-based clustering (so two reports of one root cause merge "
        "even when their codes differ) and detection of a proposal that "
        "duplicates an already-shipped skill.",
    ),
)

BRIDGES: dict[str, BridgeSpec] = {row.skill_id: row for row in _ROWS}

_UNKNOWN = sorted(set(BRIDGES) - set(SKILL_SPECS))
if _UNKNOWN:  # pragma: no cover - guarded at import
    raise RuntimeError(f"kernel bridge names skills outside the v2 catalog: {_UNKNOWN}")


def engine_for(skill: str) -> str:
    """Which engine is configured to answer ``skill``."""

    return "kernel" if skill in BRIDGES else "legacy"


#: Why each remaining skill answers from the legacy engine.
#:
#: A routed row carries its rationale in ``BRIDGES``; an unrouted one carried
#: nothing, so an operator asking "why is this one still on the old engine?" got
#: silence - and silence reads as "nobody looked yet" whether or not anybody
#: did.  Three of these are decisions rather than backlog, and the distinction
#: is the point of writing them down.
#:
#: ``blocked`` marks a row that must NOT be promoted as the core stands.  The
#: others are translation gaps: the core refuses the v2 payload at decode level,
#: which is a statement about this bridge and not about either engine.
LEGACY_RATIONALES: Mapping[str, Mapping[str, Any]] = {
    "typed-tool-runtime": {
        "blocked": True,
        "reason": (
            "the two engines do different things and only one of them runs the tool. "
            "The legacy handler calls ToolRuntime.invoke and the tool executes. The "
            "core's registry entry point wires a _StaticInvoker over the caller's own "
            "`tool_output` field: it validates the call against the descriptor's ABI, "
            "checks the authority and the policy snapshot, and records the result - it "
            "never invokes anything. Routing a v2 caller here would return a SUCCEEDED "
            "tool-call record, with an idempotency key and a state machine behind it, "
            "for a tool that never ran; the 'output' would be the empty default they "
            "did not supply. That is the single most damaging promotion available in "
            "this package. The core's depth here is real and belongs in-process, "
            "driving a live ToolInvoker - not over a JSON dispatcher whose callers "
            "expect execution."
        ),
    },
    "two-phase-secretless-sandbox": {
        "blocked": True,
        "reason": (
            "same shape as typed-tool-runtime, on the security surface. The core "
            "requires `runner_result` - it decides and attests, and the docstring says "
            "outright that it never spawns. The v2 payload plans an execution that has "
            "not happened: repository snapshot, workspace profile, network policy, "
            "secret binding plan. Promoting would mean synthesising a runner result, "
            "i.e. attesting a sandboxed execution that never occurred. The legacy "
            "planner is honest about being a plan (`sandbox_attestation.status: "
            "PLANNED`, `cleanup_report.status: PENDING`) and enforces two real "
            "invariants - the analyse phase cannot bind secrets, and the network policy "
            "must deny by default. Its weakness is uuid4 sandbox ids, so two identical "
            "calls disagree."
        ),
    },
    "tiered-security-assurance": {
        "blocked": True,
        "reason": (
            "the core assesses an effective tier against `control_reports` and expiring "
            "`waivers`, and raises SECURITY_GATE_FAILED for any non-PASS. A v2 payload "
            "supplies neither - it has a change, a diff, a semantic index and a policy - "
            "so every promoted call would fail closed on 'the required controls did not "
            "run'. A gate that refuses every request is not a strict gate; it is the "
            "placeholder-pin failure wearing a security label, and it would train "
            "operators to route around it. Legacy is two regexes over the diff plus a "
            "'did the deployment artifact claim this layer passed' lookup, which is "
            "shallow but fail-closed and reports NOT_RUN as NOT_RUN."
        ),
    },
    "semantic-ir-compiler": {
        "blocked": False,
        "reason": (
            "different operation, not a shape gap. The core compiles one "
            "`sourceUnit.source` into typed IR and admits python only, refusing any "
            "other language with TARGET_PROFILE_UNSUPPORTED. The v2 skill compiles a "
            "whole semantic index across framework profiles. The legacy path now "
            "reports PARTIAL with a status note rather than claiming COMPILED, which "
            "was the actual defect here and is fixed."
        ),
    },
    "phase-aware-model-router": {
        "blocked": False,
        "reason": (
            "a translation gap that cannot be closed without fabricating numbers. The "
            "core ranks on Decimal prices per million tokens, an explicit tier, a max "
            "output and a reliability prior in [0,1], and hashes the decision so two "
            "hosts cannot disagree. A v2 profile has `cost_per_call` (a different unit, "
            "convertible only with a token count nobody supplies), `eval_status` (a "
            "PASS/FAIL gate, not a prior) and no tier or max output at all. Inventing "
            "those is inventing the very numbers the ranking's reproducibility rests "
            "on. Legacy's own defects are now stamped on its output instead: float "
            "scoring that two hosts can order differently, and an unpriced model scored "
            "as free and therefore ranked above every priced one."
        ),
    },
    "prefix-stable-context-planner": {
        "blocked": False,
        "reason": (
            "translation gap. The core wants each named input as a block descriptor "
            "carrying a digest and a token cost; v2 passes the objects themselves. The "
            "digest is derivable from the object, the token cost is not - it depends on "
            "a tokenizer nobody named, and an estimate would be a fabricated "
            "measurement in a planner whose whole job is fitting a budget."
            " Legacy takes an integer `token_budget` and plans against it without ever "
            "measuring a block, so its plan fits the budget by assertion."
        ),
    },
    "model-state-continuity": {
        "blocked": False,
        "reason": (
            "translation gap: the core reads `compaction_policy`, `binding`, "
            "`decisions` and `checkpoint_id`; v2 sends `run_state`, `agent_state`, "
            "`tool_results` and `open_findings`. The two describe the same situation "
            "from opposite ends - the core asks what may be dropped and what must "
            "survive a provider switch, v2 hands over the state itself - so the adapter "
            "has to decide which v2 fields are load-bearing rather than rename them. "
            "Legacy already reports `resume_equivalence_checked: false`, so it is not "
            "claiming the guarantee the core would add. Adaptable, not yet adapted."
        ),
    },
    "lazy-tool-loader": {
        "blocked": False,
        "reason": (
            "translation gap: the core wants `tool_catalogue` plus a `task_profile` "
            "with requiredCapabilities, tokenBudget and maxTools; v2 sends "
            "`tool_catalog` and a flat `step_requirements` list with no budget. The "
            "budget is the missing half rather than a missing name - the core's job is "
            "to load the fewest tools that cover the required capabilities within a "
            "token ceiling, and with no ceiling stated there is nothing to trade off. "
            "Defaulting one would set the caller's context budget on their behalf."
        ),
    },
    "capability-package-registry": {
        "blocked": False,
        "reason": (
            "translation gap: the core is a lifecycle - package, promotion request, "
            "evaluation report, installation, revocation - while v2 sends a manifest "
            "with components, a lock, a signature and test results in one call. "
            "Collapsing the lifecycle into that single call means choosing which stage "
            "the caller meant, and the stages differ in what they are allowed to do: "
            "registering is not promoting, and promoting is what the evidence and the "
            "approver exist to gate."
        ),
    },
    "multi-agent-worktree-coordinator": {
        "blocked": False,
        "reason": (
            "translation gap plus live ports, like the lease kernel: the core requires "
            "a `ports` mapping because a coordinator with its own in-memory lease store "
            "would hand out worktrees it does not own. Needs a store adapter of the same "
            "shape as the leasing row, which is the reason it is last rather than the "
            "reason it cannot be done."
        ),
    },
}


def engine_report() -> dict[str, Any]:
    """A machine-readable statement of who serves what, and why.

    Exposed on the control plane so an operator can answer "which
    implementation produced this?" without reading the source.
    """

    return {
        "kernelServed": sorted(BRIDGES),
        "legacyServed": sorted(set(SKILL_SPECS) - set(BRIDGES)),
        "rationales": {row.skill_id: row.rationale for row in _ROWS},
        "legacyRationales": {
            skill: dict(entry) for skill, entry in sorted(LEGACY_RATIONALES.items())
        },
        "counts": {
            "kernel": len(BRIDGES),
            "legacy": len(SKILL_SPECS) - len(BRIDGES),
            "legacyBlocked": sum(
                1 for entry in LEGACY_RATIONALES.values() if entry["blocked"]),
            "total": len(SKILL_SPECS),
        },
    }


def _as_kernel_error(error: Mapping[str, Any], skill: str) -> KernelError:
    """Re-raise a kernel failure envelope as this package's error type.

    The two packages each have a ``KernelError`` and the dispatcher only
    understands its own.  Translating rather than wrapping keeps the code -
    ``ILLEGAL_TRANSITION``, ``SCOPE_ESCALATION_ATTEMPT``, ``LEASE_HELD_BY_OTHER`` -
    intact all the way to the caller, which is the only reason a domain rejection
    is worth preserving in the first place.
    """

    body = dict(error)
    return KernelError(ErrorInfo(
        code=str(body.get("code", "INTERNAL_ERROR")),
        category=str(body.get("category", "capability-specific")),
        retryable=bool(body.get("retryable", False)),
        partial=bool(body.get("partial", False)),
        interrupted=bool(body.get("interrupted", False)),
        evidence_ids=tuple(body.get("evidenceIds", ())),
        recommended_action=str(body.get("recommendedAction", "")),
        details={"engine": "kernel", "skill": skill,
                 "message": str(body.get("message", "")),
                 **dict(body.get("details", {}))},
    ))


def serve(skill: str, payload: Mapping[str, Any], context: Any = None) -> BridgeOutcome:
    """Answer ``skill`` from the kernel, or say why the legacy engine should.

    Three outcomes, and the middle one is the interesting one:

    * **served** - the kernel computed the answer.
    * **not served** - the kernel could not *read* this payload (a decode-level
      code, or its own NOT_APPLICABLE).  The legacy engine answers and the
      reason is carried out so the gap is countable rather than invisible.  A
      caller who was talking to the legacy engine correctly does not break
      because a deeper engine was installed underneath it.
    * **raised** - the kernel read the payload and rejected the *domain*.  That
      rejection stands: letting the shallower engine overturn it would be worse
      than having no kernel at all.

    ``context`` is the dispatcher's ``DispatchContext``, passed because four of
    these skills cannot build a request without it: the lease kernel refuses to
    run without a live store, and the orchestrator's answer has to be written
    into one.  It is optional so that ``serve`` stays callable on its own, in
    which case only the payload-only adapters can promote anything.

    Persistence obeys the same rule as the kernel itself: a ``persist_outputs``
    hook that fails raises.  Falling back to the legacy engine at that point
    would re-run a side-effecting handler after the kernel had already produced
    an answer, which is how one run becomes two.
    """

    spec = BRIDGES.get(skill)
    if spec is None:
        return BridgeOutcome(served=False)

    request = spec.request_for(payload, context)
    if not request:
        return BridgeOutcome(served=False, reasons=("KERNEL_INPUT_UNMAPPED:EMPTY_REQUEST",))

    binding = spec.bind_stores(context, request) if spec.bind_stores is not None else nullcontext()
    with binding:
        result = kernel_dispatch(skill, request)

    if result.status is KernelStatus.NOT_APPLICABLE:
        return BridgeOutcome(served=False, reasons=("KERNEL_NOT_APPLICABLE",))

    if result.status not in _ANSWERED:
        code = str((result.error or {}).get("code", "INTERNAL_ERROR"))
        if code in DECODE_LEVEL_CODES:
            return BridgeOutcome(
                served=False, reasons=(f"KERNEL_INPUT_UNMAPPED:{code}",))
        raise _as_kernel_error(result.error or {}, skill)

    outputs = spec.outputs_for(payload, result.outputs)
    reasons = ["ENGINE:kernel"]
    if spec.persist_outputs is not None:
        try:
            outputs, persistence = spec.persist_outputs(context, payload, outputs)
        except _KernelSideError as exc:
            raise _as_kernel_error(exc.to_payload(), skill) from exc
        reasons.append(persistence)
    if result.status is KernelStatus.PARTIAL:
        reasons.append("KERNEL_PARTIAL")

    if spec.publish_context is not None and context is not None:
        published = spec.publish_context(context, outputs)
        if published:
            reasons.append(published)

    status = _STATUS_MAP[result.status]
    if spec.blocked_when is not None:
        blocked = spec.blocked_when(outputs)
        if blocked:
            # Only ever towards BLOCKED.  A hook that could clear a block would
            # be a way for the bridge to overrule a verdict, which is the thing
            # the whole no-downgrade rule exists to prevent.
            status = Status.BLOCKED
            reasons.append(blocked)
    return BridgeOutcome(served=True, status=status,
                         output=dict(outputs), reasons=tuple(reasons))
