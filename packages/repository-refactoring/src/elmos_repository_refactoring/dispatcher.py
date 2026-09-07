"""The closed dispatcher: exact Skill names in, :class:`HandlerResult` out.

Rules the dispatcher enforces for every Skill, so no individual handler has to
remember them:

* the Skill name must be in the catalog — unknown work fails closed;
* the payload must be an object, and server-owned fields may not be supplied
  by a caller;
* filesystem reach comes from the *trusted context*, never from the payload;
* a handler that raises :class:`ContractError` produces a structured rejection
  rather than a traceback;
* an unexpected exception is reported as ``failed`` with a terminal failure
  class and never as a partial success.

:data:`PENDING_SKILLS` names catalog entries whose production handler has not
landed yet.  They dispatch to an explicit ``blocked`` result — never a stub that
returns success — and the acceptance suite asserts the set is empty before the
package may claim full coverage.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from . import anticheat, apicompat, client, contractsmig, distributed, performance, program, security, sqlops
from . import registry as recipe_registry
from .adapters import AdapterCapabilitySnapshot
from .approval import (
    ApprovalRecord,
    BoundDigests,
    audit_record,
    build_context,
    evaluate_approvals,
    request_approval,
)
from .buildgraph import (
    BaselineReport,
    BuildGraph,
    build_graph,
    establish_baseline,
    sandbox_image_spec,
    toolchain_lock,
)
from .catalog import SKILL_NAMES, SKILL_SPECS, resolve_skill_name
from .contracts import (
    ContractError,
    ExecutionMode,
    FailureClass,
    HandlerResult,
    RecipeStatus,
    RiskClass,
    Status,
    integer_value,
    optional_mapping,
    optional_string,
    parse_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_mapping,
    require_sequence,
    require_string,
    require_string_sequence,
    sha256_payload,
)
from .discovery import (
    RepositoryInventory,
    discover,
    discovery_evidence,
    language_inventory_payload,
    sensitive_area_map,
)
from .evidence import (
    BundleInputs,
    CostBreakdown,
    GateDecisionRecord,
    artifact_from_payload,
    artifact_from_text,
    assemble,
    audit_timeline,
    billing_breakdown,
    verify_bundle,
)
from .evidence import sign as sign_bundle
from .executor import execute_transform
from .impact import analyse_impact
from .index import SemanticIndex, build_index
from .intent import CompiledIntent, compile_intent
from .journal import RunJournal
from .orchestrator import RefactorRun, synthesize_plan
from .patch import diff_snapshots
from .policy import RefactorPolicy, resolve_policy
from .recipe import Recipe
from .recovery import (
    build_incident_report,
    execute_rollback,
    last_consistent_checkpoint,
    plan_rollback,
    reconcile,
    recovery_summary,
)
from .repair import attribute_to_actions, budget_from_request, normalise_failures
from .repair import repair as repair_failures
from .request import RefactorRequest
from .rollout import (
    GuardrailReading,
    plan_rollout,
    release_evidence,
    run_ladder,
    split_changesets,
)
from .sandbox import ExecutionKind, ExecutionRequest, NullExecutor, RecordedExecutor, SandboxExecutor
from .synthesis import predicate_context, registry_payload, synthesize
from .verification import junit_payload, verify
from .workspace import WorkspaceSnapshot, snapshot_from_context

#: Skills whose production handler is not wired yet.  Empty is the goal state.
PENDING_SKILLS: frozenset[str] = frozenset()


def _evaluation_from_payload(digest: str, entry: Mapping[str, Any]) -> recipe_registry.EvaluationReport:
    """Parse one corpus evaluation, refusing anything a promotion cannot rest on."""

    try:
        return recipe_registry.EvaluationReport(
            recipe_reference=require_string(entry.get("recipe"), "evaluation.recipe"),
            recipe_digest=digest,
            corpus_digest=require_string(entry.get("corpusDigest"), "evaluation.corpusDigest"),
            true_positives=integer_value(entry.get("truePositives", 0), "evaluation.truePositives", minimum=0),
            false_positives=integer_value(entry.get("falsePositives", 0), "evaluation.falsePositives", minimum=0),
            false_negatives=integer_value(entry.get("falseNegatives", 0), "evaluation.falseNegatives", minimum=0),
            escape_defects=integer_value(entry.get("escapeDefects", 0), "evaluation.escapeDefects", minimum=0),
            idempotent=bool(entry.get("idempotent", False)),
            repositories=tuple(require_string_sequence(entry.get("repositories", ()), "evaluation.repositories")),
            adversarial_fixtures=integer_value(
                entry.get("adversarialFixtures", 0), "evaluation.adversarialFixtures", minimum=0
            ),
            cost_units=Decimal(str(entry.get("costUnits", 0))),
        )
    except ArithmeticError as error:
        raise ContractError("invalid_evaluation", "evaluation.costUnits must be numeric") from error


def _dependency_map(graph: BuildGraph) -> dict[str, dict[str, str]]:
    """Declared dependencies per build system, as a coarse SBOM stand-in.

    The build graph records *what* is depended on, not always at which
    version; entries with no version resolve to an empty string, which
    :func:`security.sbom_delta` treats as a change of unknown direction
    rather than as an unchanged pin.
    """

    grouped: dict[str, dict[str, str]] = {}
    for target in graph.targets:
        bucket = grouped.setdefault(target.build_system, {})
        for dependency in target.dependencies:
            name, _, version = dependency.partition("@")
            bucket.setdefault(name, version)
    return grouped


@dataclass(frozen=True, slots=True)
class _Pipeline:
    """The recomputed analysis chain shared by the planning-stage handlers."""

    snapshot: WorkspaceSnapshot
    inventory: RepositoryInventory
    graph: BuildGraph
    index: SemanticIndex
    request: RefactorRequest
    intent: CompiledIntent


@dataclass(frozen=True, slots=True)
class DispatchContext:
    """Host-owned authority, kept structurally separate from task payloads."""

    policy: RefactorPolicy | None = None
    adapters: AdapterCapabilitySnapshot | None = None
    executor: SandboxExecutor | None = None
    approved_workspace_root: Path | None = None
    approved_journal_root: Path | None = None
    now: datetime | None = None

    @property
    def resolved_policy(self) -> RefactorPolicy:
        return self.policy or resolve_policy(None)

    @property
    def resolved_adapters(self) -> AdapterCapabilitySnapshot:
        return self.adapters or AdapterCapabilitySnapshot()

    @property
    def resolved_executor(self) -> SandboxExecutor:
        return self.executor or NullExecutor()


Handler = Callable[[str, Mapping[str, Any], DispatchContext], HandlerResult]


def build_trusted_context(value: Mapping[str, Any] | None = None) -> DispatchContext:
    """Build a :class:`DispatchContext` from a host-supplied mapping.

    Every field here widens what the runtime may reach, which is exactly why it
    is parsed separately from the task payload and rejects unknown keys.
    """

    raw = require_mapping({} if value is None else value, "trusted_context")
    reject_unknown_fields(
        raw,
        {
            "policy",
            "policy_ref",
            "adapter_capabilities",
            "recorded_executions",
            "workspace_root",
            "journal_root",
            "now",
        },
        "trusted_context",
    )
    policy_payload = raw.get("policy")
    policy = resolve_policy(
        None if policy_payload is None else require_mapping(policy_payload, "trusted_context.policy"),
        reference=optional_string(raw.get("policy_ref"), "trusted_context.policy_ref"),
    )
    adapters = AdapterCapabilitySnapshot.from_payload(
        None if raw.get("adapter_capabilities") is None else require_mapping(
            raw["adapter_capabilities"], "trusted_context.adapter_capabilities"
        )
    )
    executor: SandboxExecutor = NullExecutor()
    recordings = raw.get("recorded_executions")
    if recordings is not None:
        if not isinstance(recordings, Sequence) or isinstance(recordings, str | bytes):
            raise ContractError("invalid_array", "trusted_context.recorded_executions must be an array")
        executor = RecordedExecutor.from_payload(
            [require_mapping(item, "trusted_context.recorded_executions[]") for item in recordings]
        )
    #: Pinning the clock is what makes a timestamped Skill reproducible.  It
    #: lives in trusted context, not in the payload: a caller that could set
    #: the time on an audit record could date an approval into the past.
    moment = raw.get("now")
    pinned = (
        None
        if moment is None
        else parse_timestamp(require_string(moment, "trusted_context.now"), "trusted_context.now")
    )
    return DispatchContext(
        policy=policy,
        adapters=adapters,
        executor=executor,
        approved_workspace_root=_approved_directory(raw.get("workspace_root"), "trusted_context.workspace_root"),
        approved_journal_root=_approved_directory(raw.get("journal_root"), "trusted_context.journal_root"),
        now=pinned,
    )


def _approved_directory(value: Any, field_name: str) -> Path | None:
    if value is None:
        return None
    text = optional_string(value, field_name, max_length=4096)
    if text is None:
        return None
    candidate = Path(text)
    if not candidate.is_absolute():
        raise ContractError("root_not_absolute", f"{field_name} must be an absolute path")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ContractError("root_unavailable", f"{field_name} does not exist") from exc
    if not resolved.is_dir():
        raise ContractError("root_not_directory", f"{field_name} must be a directory")
    return resolved


class RuntimeDispatcher:
    """Dispatch exactly the catalog; refuse everything else."""

    __slots__ = ("_handlers",)

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}
        for name in SKILL_NAMES:
            spec = SKILL_SPECS[name]
            handler = getattr(self, spec.handler, None)
            if callable(handler):
                self._handlers[name] = handler
            elif name in PENDING_SKILLS:
                self._handlers[name] = self._pending
            else:
                raise RuntimeError(f"missing runtime handler '{spec.handler}' for skill '{name}'")
        if set(self._handlers) != set(SKILL_NAMES):
            raise RuntimeError("dispatcher coverage must equal the exact skill catalog")

    @property
    def handler_names(self) -> tuple[str, ...]:
        return SKILL_NAMES

    @property
    def implemented(self) -> tuple[str, ...]:
        return tuple(name for name in SKILL_NAMES if name not in PENDING_SKILLS)

    # -- envelope --------------------------------------------------------

    def _result(
        self,
        skill: str,
        status: Status,
        output: Mapping[str, Any] | None = None,
        reasons: Sequence[str] = (),
        *,
        failure_class: FailureClass | None = None,
        side_effects_performed: bool = False,
        evidence: Mapping[str, Any] | None = None,
        risk_class: RiskClass | None = None,
    ) -> HandlerResult:
        spec = SKILL_SPECS[skill]
        return HandlerResult(
            skill=skill,
            status=status,
            output=output or {},
            reasons=tuple(reasons),
            canonical_owner=spec.canonical_owner,
            risk_class=risk_class or spec.risk_class,
            failure_class=failure_class,
            side_effects_performed=side_effects_performed,
            evidence=evidence or {},
        )

    def execute(
        self,
        skill_name: str,
        payload: Mapping[str, Any] | None = None,
        *,
        context: DispatchContext | None = None,
    ) -> HandlerResult:
        try:
            resolved = resolve_skill_name(skill_name)
        except ContractError as error:
            return HandlerResult(
                skill=str(skill_name),
                status=Status.REJECTED,
                reasons=(error.message,),
                failure_class=FailureClass.TERMINAL,
                output=error.to_payload(),
            )
        active = context or DispatchContext()
        try:
            body = require_mapping({} if payload is None else payload, "payload")
            return self._handlers[resolved](resolved, body, active)
        except ContractError as error:
            return self._result(
                resolved,
                Status.REJECTED,
                error.to_payload(),
                (error.message,),
                failure_class=FailureClass.TERMINAL,
            )
        except RecursionError:
            return self._result(
                resolved,
                Status.FAILED,
                {"code": "recursion_limit"},
                ("input nesting exceeded the interpreter recursion limit",),
                failure_class=FailureClass.TERMINAL,
            )
        except Exception as error:  # noqa: BLE001 - the boundary must not leak a traceback
            return self._result(
                resolved,
                Status.FAILED,
                {
                    "code": "unhandled_exception",
                    "type": type(error).__name__,
                    "frames": len(traceback.extract_tb(error.__traceback__)),
                },
                (f"unhandled {type(error).__name__} in handler for '{resolved}'",),
                failure_class=FailureClass.TERMINAL,
            )

    def _pending(self, skill: str, payload: Mapping[str, Any], context: DispatchContext) -> HandlerResult:
        return self._result(
            skill,
            Status.BLOCKED,
            {"code": "handler_not_implemented", "skill": skill},
            (
                f"the production handler for '{skill}' is not wired in this build; "
                "it fails closed rather than returning an unearned success",
            ),
            failure_class=FailureClass.TERMINAL,
        )

    # -- shared payload helpers ------------------------------------------

    def _snapshot(self, payload: Mapping[str, Any], context: DispatchContext) -> WorkspaceSnapshot:
        workspace = payload.get("workspace")
        if workspace is None:
            raise ContractError("missing_workspace", "payload.workspace is required")
        return snapshot_from_context(
            require_mapping(workspace, "payload.workspace"),
            approved_root=context.approved_workspace_root,
        )

    def _inventory(
        self,
        payload: Mapping[str, Any],
        context: DispatchContext,
        snapshot: WorkspaceSnapshot,
    ) -> RepositoryInventory:
        return discover(
            snapshot,
            include=require_string_sequence(payload.get("include", ()), "payload.include"),
            exclude=require_string_sequence(payload.get("exclude", ()), "payload.exclude"),
        )

    def _pipeline(self, payload: Mapping[str, Any], context: DispatchContext) -> _Pipeline:
        """Rebuild the analysis chain deterministically from the payload.

        Recomputing rather than accepting a caller-supplied index is what keeps
        every later stage bound to a snapshot the runtime has actually seen: a
        supplied index could describe a tree that no longer exists.
        """

        snapshot = self._snapshot(payload, context)
        inventory = self._inventory(payload, context, snapshot)
        graph = build_graph(snapshot, inventory)
        index = build_index(snapshot, inventory, graph)
        request = RefactorRequest.from_payload(require_mapping(payload.get("request"), "payload.request"))
        intent = compile_intent(request, index, unknown_risk_weight=index.coverage.unknown_risk_weight)
        return _Pipeline(
            snapshot=snapshot,
            inventory=inventory,
            graph=graph,
            index=index,
            request=request,
            intent=intent,
        )

    # -- Skill 00 --------------------------------------------------------

    def repository_refactor_orchestrator(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"request", "run_id", "action", "snapshot_digests", "events", "plan", "running", "unknown_risk_weight"},
            "payload",
        )
        request = RefactorRequest.from_payload(require_mapping(payload.get("request"), "payload.request"))
        policy = context.resolved_policy
        run_id = require_identifier(payload.get("run_id", "run-local"), "payload.run_id")
        action = optional_string(payload.get("action"), "payload.action") or "plan"

        if not policy.permits_mode(request.execution.mode):
            return self._result(
                skill,
                Status.REJECTED,
                {"mode": request.execution.mode.value, "allowed": [m.value for m in policy.allowed_modes]},
                (f"policy '{policy.name}' does not permit execution mode '{request.execution.mode.value}'",),
                failure_class=FailureClass.APPROVAL_REQUIRED,
            )
        if request.execution.mode is ExecutionMode.AUTONOMOUS_LOW_RISK:
            unmet = _autonomy_blockers(request, policy, context.resolved_adapters)
            if unmet:
                return self._result(
                    skill,
                    Status.BLOCKED,
                    {"unmetAutonomyRequirements": list(unmet)},
                    unmet,
                    failure_class=FailureClass.APPROVAL_REQUIRED,
                )

        digests = {
            key: value
            for key, value in optional_mapping(payload.get("snapshot_digests"), "payload.snapshot_digests").items()
        }
        from decimal import Decimal

        weight_raw = payload.get("unknown_risk_weight", 0)
        weight = Decimal(str(weight_raw))
        plan = synthesize_plan(
            request,
            policy,
            run_id=run_id,
            snapshot_digests=digests,
            unknown_risk_weight=weight,
        )
        journal = RunJournal(run_id)
        run = RefactorRun(request, policy, run_id=run_id, journal=journal, now=context.now)
        run.freeze_plan(plan, now=context.now)

        events = payload.get("events")
        if events is not None:
            replay_events = [
                require_mapping(item, "payload.events[]")
                for item in require_sequence(events, "payload.events")
            ]
            run = RefactorRun.replay(request, policy, plan, replay_events)

        if action == "plan":
            output = {
                "plan": plan.to_payload(),
                "planDigest": plan.digest,
                "waves": [list(wave) for wave in plan.waves()],
                "criticalPath": list(plan.critical_path()[0]),
                "conflicts": [
                    {"left": left, "right": right, "reason": reason} for left, right, reason in plan.conflicts()
                ],
                "run": run.to_payload(),
            }
        elif action == "schedule":
            decision = run.schedule(running=require_string_sequence(payload.get("running", ()), "payload.running"))
            output = {"schedule": decision.to_payload(), "progress": run.progress()}
        elif action == "progress":
            output = {"progress": run.progress(), "timeline": list(run.journal.timeline())}
        else:
            raise ContractError("unknown_action", "payload.action must be plan, schedule or progress")

        return self._result(
            skill,
            Status.SUCCEEDED,
            output,
            evidence={"journalHead": run.journal.head_digest, "policyDigest": policy.digest},
            risk_class=plan.risk_summary.overall_class,
        )

    # -- Skill 01 --------------------------------------------------------

    def repository_discovery(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(payload, {"workspace", "include", "exclude"}, "payload")
        snapshot = self._snapshot(payload, context)
        inventory = self._inventory(payload, context, snapshot)
        evidence = discovery_evidence(inventory)
        blocked_paths = sorted(
            {path for path in snapshot.paths if context.resolved_policy.forbids(path) is not None}
        )
        return self._result(
            skill,
            Status.SUCCEEDED,
            {
                "repository_inventory": inventory.to_payload(),
                "language_inventory": language_inventory_payload(inventory),
                "sensitive_area_map": sensitive_area_map(inventory),
                "discovery_evidence": evidence.to_payload(),
                "policyForbiddenPaths": blocked_paths,
            },
            evidence.warnings,
            evidence={"inventoryDigest": inventory.digest, "treeDigest": snapshot.tree_digest},
        )

    # -- Skill 02 --------------------------------------------------------

    def build_graph_and_environment(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(payload, {"workspace", "include", "exclude", "baseline_profile"}, "payload")
        snapshot = self._snapshot(payload, context)
        inventory = self._inventory(payload, context, snapshot)
        graph = build_graph(snapshot, inventory)
        lock = toolchain_lock(snapshot, graph)
        baseline: BaselineReport = establish_baseline(
            graph,
            context.resolved_executor,
            profile=optional_string(payload.get("baseline_profile"), "payload.baseline_profile") or "default",
        )
        image = sandbox_image_spec(inventory, lock, network=context.resolved_policy.sandbox.network.value)

        reasons: list[str] = []
        if not lock.reproducible:
            reasons.append(
                "unpinned dependency closure for: " + ", ".join(lock.unpinned) + "; restore is not reproducible"
            )
        if not baseline.trustworthy:
            reasons.append(
                f"baseline was not established ({baseline.status.value}: {baseline.reason or 'no executor'}); "
                "post-change comparisons cannot distinguish regressions from pre-existing failures"
            )
        if graph.unmapped_files:
            reasons.append(f"{len(graph.unmapped_files)} file(s) map to no build target")
        if graph.heuristic_targets:
            reasons.append(
                f"{len(graph.heuristic_targets)} target(s) come from heuristic parsers (Gradle DSL / CMake)"
            )

        return self._result(
            skill,
            Status.SUCCEEDED,
            {
                "build_graph": graph.to_payload(),
                "toolchain_lock": lock.to_payload(),
                "baseline_report": baseline.to_payload(),
                "sandbox_image_spec": image.to_payload(),
            },
            reasons,
            evidence={
                "buildGraphDigest": graph.digest,
                "toolchainLockDigest": lock.digest,
                "sandboxImageDigest": image.digest,
                "executor": context.resolved_executor.name,
            },
        )

    # -- Skill 03 --------------------------------------------------------

    def semantic_index(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(payload, {"workspace", "include", "exclude", "include_generated"}, "payload")
        snapshot = self._snapshot(payload, context)
        inventory = self._inventory(payload, context, snapshot)
        graph = build_graph(snapshot, inventory)
        index = build_index(
            snapshot,
            inventory,
            graph,
            include_generated=bool(payload.get("include_generated", False)),
        )
        adapters = context.resolved_adapters
        languages = {item.language for item in inventory.languages}
        levels = {language: adapters.effective_level(language).value for language in sorted(languages)}
        reasons: list[str] = []
        if index.coverage.unknown_risk_weight > 0:
            reasons.append(
                f"unknown-risk weight {index.coverage.unknown_risk_weight}: "
                f"{len(index.unknown_regions)} unindexed path(s), {index.coverage.dynamic_files} file(s) with "
                "dynamic references"
            )
        inventory_only = sorted(name for name, level in levels.items() if level == "L0")
        if inventory_only:
            reasons.append("inventory-only languages (no automatic edits permitted): " + ", ".join(inventory_only))
        return self._result(
            skill,
            Status.SUCCEEDED,
            {
                "semantic_index_snapshot": index.to_payload(),
                "coverage_metrics": index.coverage.to_payload(),
                "unknown_region_report": index.unknown_region_report(),
                "adapter_levels": levels,
            },
            reasons,
            evidence={"indexDigest": index.digest, "treeDigest": snapshot.tree_digest},
        )


    # -- Skill 04 --------------------------------------------------------

    def refactor_intent_compiler(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(payload, {"workspace", "include", "exclude", "request"}, "payload")
        pipeline = self._pipeline(payload, context)
        intent = pipeline.intent
        reasons: list[str] = []
        for conflict in intent.conflicts:
            reasons.append("constraint conflict: " + ", ".join(conflict.minimal_set) + " — " + conflict.explanation)
        for assumption in intent.blocking_assumptions:
            reasons.append(f"assumption '{assumption.id}' requires approval: {assumption.statement}")
        for goal in intent.unclassified_goals:
            reasons.append(f"goal {goal.index} could not be classified: {goal.text}")
        status = Status.SUCCEEDED if intent.executable else Status.BLOCKED
        return self._result(
            skill,
            status,
            {
                "compiled_intent": intent.to_payload(),
                "acceptance_predicates": [item.to_payload() for item in intent.predicates],
                "assumption_register": [item.to_payload() for item in intent.assumptions],
                "scope_policy": intent.scope.to_payload(),
            },
            reasons,
            failure_class=None if intent.executable else FailureClass.APPROVAL_REQUIRED,
            evidence={"intentDigest": intent.digest, "indexDigest": pipeline.index.digest},
            risk_class=intent.risk_floor,
        )

    # -- Skill 05 --------------------------------------------------------

    def change_impact_analysis(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(payload, {"workspace", "include", "exclude", "request", "max_distance"}, "payload")
        pipeline = self._pipeline(payload, context)
        report = analyse_impact(
            pipeline.intent,
            pipeline.index,
            pipeline.graph,
            pipeline.inventory,
            max_distance=integer_value(payload.get("max_distance", 6), "payload.max_distance", minimum=1, maximum=32),
        )
        reasons = list(report.risk.reasons)
        if report.closure.truncated:
            reasons.append("the change closure is truncated; treat the impact set as a lower bound")
        return self._result(
            skill,
            Status.SUCCEEDED,
            {
                "impact_report": report.to_payload(),
                "change_closure": report.closure.to_payload(),
                "test_selection_plan": report.tests.to_payload(),
                "wave_plan": [wave.to_payload() for wave in report.waves],
                "risk_assessment": report.risk.to_payload(),
            },
            reasons,
            evidence={"impactDigest": report.digest, "indexDigest": pipeline.index.digest},
            risk_class=report.risk.risk_class,
        )

    # -- Skill 06 --------------------------------------------------------

    def recipe_synthesis(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"workspace", "include", "exclude", "request", "explicit_recipes", "allow_draft", "dry_run"},
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        explicit: list[tuple[str, Mapping[str, Any]]] = []
        for item in require_sequence(payload.get("explicit_recipes", ()), "payload.explicit_recipes"):
            entry = require_mapping(item, "payload.explicit_recipes[]")
            reject_unknown_fields(entry, {"reference", "parameters"}, "payload.explicit_recipes[]")
            explicit.append(
                (
                    require_string(entry.get("reference"), "payload.explicit_recipes[].reference"),
                    require_mapping(entry.get("parameters", {}), "payload.explicit_recipes[].parameters"),
                )
            )
        result = synthesize(
            pipeline.intent,
            pipeline.snapshot,
            pipeline.index,
            context.resolved_adapters,
            explicit=tuple(explicit),
            allow_draft=bool(payload.get("allow_draft", False)),
            dry_run=bool(payload.get("dry_run", True)),
        )
        status = Status.SUCCEEDED if result.executable else Status.BLOCKED
        return self._result(
            skill,
            status,
            {**result.to_payload(), "registry": registry_payload()},
            result.reasons,
            failure_class=None if result.executable else FailureClass.APPROVAL_REQUIRED,
            evidence={"recipeLockDigest": result.lock.digest, "synthesisDigest": result.digest},
        )

    # -- Skill 07 --------------------------------------------------------

    def deterministic_transform_executor(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"workspace", "include", "exclude", "request", "explicit_recipes", "allow_draft", "step_id"},
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        if not pipeline.request.execution.mode.mutates_workspace:
            return self._result(
                skill,
                Status.REJECTED,
                {"mode": pipeline.request.execution.mode.value},
                (
                    f"execution mode '{pipeline.request.execution.mode.value}' does not permit "
                    "workspace mutation",
                ),
                failure_class=FailureClass.TERMINAL,
            )
        explicit: list[tuple[str, Mapping[str, Any]]] = []
        for item in require_sequence(payload.get("explicit_recipes", ()), "payload.explicit_recipes"):
            entry = require_mapping(item, "payload.explicit_recipes[]")
            reject_unknown_fields(entry, {"reference", "parameters"}, "payload.explicit_recipes[]")
            explicit.append(
                (
                    require_string(entry.get("reference"), "payload.explicit_recipes[].reference"),
                    require_mapping(entry.get("parameters", {}), "payload.explicit_recipes[].parameters"),
                )
            )
        synthesis = synthesize(
            pipeline.intent,
            pipeline.snapshot,
            pipeline.index,
            context.resolved_adapters,
            explicit=tuple(explicit),
            allow_draft=bool(payload.get("allow_draft", False)),
            dry_run=False,
        )
        selected = [(item.recipe, item.parameters) for item in synthesis.selected]
        if not selected:
            return self._result(
                skill,
                Status.BLOCKED,
                {"recipeSet": [item.to_payload() for item in synthesis.candidates]},
                synthesis.reasons or ("no executable recipe was selected for this intent",),
                failure_class=FailureClass.APPROVAL_REQUIRED,
            )
        transform = execute_transform(
            selected,
            pipeline.snapshot,
            pipeline.index,
            lock=synthesis.lock,
            scope=pipeline.intent.scope,
            adapters=context.resolved_adapters,
            step_id=optional_string(payload.get("step_id"), "payload.step_id") or "transform",
            context=predicate_context(
                pipeline.intent, pipeline.index, pipeline.snapshot, synthesis.selected
            ),
        )
        status = Status.SUCCEEDED if transform.ok else Status.BLOCKED
        return self._result(
            skill,
            status,
            {
                **transform.to_payload(),
                "unifiedDiff": transform.patch.render()[:400_000],
                "recipeLockDigest": synthesis.lock.digest,
            },
            transform.blocking_reasons,
            failure_class=None if transform.ok else FailureClass.REPAIRABLE,
            side_effects_performed=False,
            evidence={
                "patchDigest": transform.patch.digest,
                "transformEvidenceDigest": transform.evidence.digest,
                "resultTreeDigest": transform.evidence.result_tree_digest,
            },
        )


    # -- shared transform stage -------------------------------------------

    def _transform_stage(
        self,
        payload: Mapping[str, Any],
        context: DispatchContext,
        pipeline: _Pipeline,
    ) -> tuple[Any, Any]:
        """Re-run synthesis and transformation so later stages see real output."""

        explicit: list[tuple[str, Mapping[str, Any]]] = []
        for item in require_sequence(payload.get("explicit_recipes", ()), "payload.explicit_recipes"):
            entry = require_mapping(item, "payload.explicit_recipes[]")
            reject_unknown_fields(entry, {"reference", "parameters"}, "payload.explicit_recipes[]")
            explicit.append(
                (
                    require_string(entry.get("reference"), "payload.explicit_recipes[].reference"),
                    require_mapping(entry.get("parameters", {}), "payload.explicit_recipes[].parameters"),
                )
            )
        synthesis = synthesize(
            pipeline.intent,
            pipeline.snapshot,
            pipeline.index,
            context.resolved_adapters,
            explicit=tuple(explicit),
            allow_draft=bool(payload.get("allow_draft", False)),
            dry_run=False,
        )
        selected = [(item.recipe, item.parameters) for item in synthesis.selected]
        transform = execute_transform(
            selected,
            pipeline.snapshot,
            pipeline.index,
            lock=synthesis.lock,
            scope=pipeline.intent.scope,
            adapters=context.resolved_adapters,
            step_id="transform",
            context=predicate_context(
                pipeline.intent, pipeline.index, pipeline.snapshot, synthesis.selected
            ),
        )
        return synthesis, transform

    def _candidate_stage(
        self,
        payload: Mapping[str, Any],
        context: DispatchContext,
        pipeline: _Pipeline,
    ) -> WorkspaceSnapshot:
        """The 'after' workspace: supplied by the host, or produced by transforming."""

        candidate_payload = payload.get("candidate_workspace")
        if candidate_payload is not None:
            return snapshot_from_context(
                require_mapping(candidate_payload, "payload.candidate_workspace"),
                approved_root=context.approved_workspace_root,
            )
        _, transform = self._transform_stage(payload, context, pipeline)
        snapshot: WorkspaceSnapshot = transform.snapshot
        return snapshot

    # -- Skill 16 --------------------------------------------------------

    def recipe_learning_registry(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"recipes", "evaluations", "signatures", "promotions", "revocations", "applications", "query"},
            "payload",
        )
        store = recipe_registry.RecipeRegistry()
        reasons: list[str] = []
        for item in require_sequence(payload.get("recipes", ()), "payload.recipes"):
            recipe = Recipe.from_payload(require_mapping(item, "payload.recipes[]"))
            store.register(recipe, owners=recipe.owners)
        for item in require_sequence(payload.get("applications", ()), "payload.applications"):
            entry = require_mapping(item, "payload.applications[]")
            store.record_application(
                require_string(entry.get("recipeDigest"), "payload.applications[].recipeDigest"),
                require_string(entry.get("runId"), "payload.applications[].runId"),
            )
        for item in require_sequence(payload.get("evaluations", ()), "payload.evaluations"):
            entry = require_mapping(item, "payload.evaluations[]")
            digest = require_string(entry.get("recipeDigest"), "payload.evaluations[].recipeDigest")
            store.record_evaluation(digest, _evaluation_from_payload(digest, entry))
        for item in require_sequence(payload.get("signatures", ()), "payload.signatures"):
            entry = require_mapping(item, "payload.signatures[]")
            store.sign(
                require_string(entry.get("recipeDigest"), "payload.signatures[].recipeDigest"),
                subject=require_string(entry.get("subject"), "payload.signatures[].subject"),
                role=require_string(entry.get("role"), "payload.signatures[].role"),
            )
        decisions: list[Mapping[str, Any]] = []
        for item in require_sequence(payload.get("promotions", ()), "payload.promotions"):
            entry = require_mapping(item, "payload.promotions[]")
            digest = require_string(entry.get("recipeDigest"), "payload.promotions[].recipeDigest")
            target_status = require_string(entry.get("target"), "payload.promotions[].target")
            try:
                target = RecipeStatus(target_status)
            except ValueError as error:
                raise ContractError(
                    "invalid_recipe_status",
                    f"unknown recipe status '{target_status}'",
                    {"supported": [value.value for value in RecipeStatus]},
                ) from error
            decision = store.promote(digest, target)
            decisions.append(decision.to_payload())
            if not decision.granted:
                reasons.extend(decision.unmet)
        for item in require_sequence(payload.get("revocations", ()), "payload.revocations"):
            entry = require_mapping(item, "payload.revocations[]")
            digest = require_string(entry.get("recipeDigest"), "payload.revocations[].recipeDigest")
            record = store.revoke(
                digest,
                reason=require_string(entry.get("reason"), "payload.revocations[].reason"),
                severity=RiskClass(str(entry.get("severity", RiskClass.R3.value))),
                reported_by=require_string(entry.get("reportedBy"), "payload.revocations[].reportedBy"),
            )
            affected = store.affected_runs(digest)
            reasons.append(
                f"revoked {record.reference}: {record.reason}"
                + (f"; {len(affected)} run(s) already applied it: {', '.join(affected)}" if affected else "")
            )
        query = optional_mapping(payload.get("query"), "payload.query") or {}
        matches = store.query(
            language=str(query.get("language", "")),
            framework=str(query.get("framework", "")),
            minimum_status=RecipeStatus(str(query["minimumStatus"]))
            if query.get("minimumStatus")
            else None,
        )
        granted = all(item.get("granted", True) for item in decisions)
        return self._result(
            skill,
            Status.SUCCEEDED if granted else Status.BLOCKED,
            {
                **store.to_payload(),
                "promotionDecisions": list(decisions),
                "matches": [item.to_payload() for item in matches],
            },
            reasons,
            failure_class=None if granted else FailureClass.APPROVAL_REQUIRED,
            evidence={"registryDigest": sha256_payload(store.to_payload())},
        )

    # -- Skill 18 --------------------------------------------------------

    def performance_preservation(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "baseline_samples",
                "candidate_samples",
                "guardrails",
                "profile_before",
                "profile_after",
                "benchmark_targets",
            },
            "payload",
        )
        baselines = [
            performance.samples_from_payload(require_mapping(item, "payload.baseline_samples[]"))
            for item in require_sequence(payload.get("baseline_samples", ()), "payload.baseline_samples")
        ]
        candidates = [
            performance.samples_from_payload(require_mapping(item, "payload.candidate_samples[]"))
            for item in require_sequence(payload.get("candidate_samples", ()), "payload.candidate_samples")
        ]
        guardrails = performance.guardrails_from_payload(
            [
                require_mapping(item, "payload.guardrails[]")
                for item in require_sequence(payload.get("guardrails", ()), "payload.guardrails")
            ]
        )
        changed: list[str] = []
        specs: tuple[performance.BenchmarkSpec, ...] = ()
        targets = require_string_sequence(
            payload.get("benchmark_targets", ()), "payload.benchmark_targets"
        )
        if targets:
            specs = performance.plan_benchmarks(targets)
        if payload.get("workspace") is not None and payload.get("request") is not None:
            pipeline = self._pipeline(payload, context)
            _, transform = self._transform_stage(payload, context, pipeline)
            changed = sorted({symbol for change in transform.patch.changes for hunk in change.hunks
                              for symbol in hunk.symbols})
        report = performance.evaluate(
            baselines,
            candidates,
            guardrails,
            profile_before=optional_mapping(payload.get("profile_before"), "payload.profile_before"),
            profile_after=optional_mapping(payload.get("profile_after"), "payload.profile_after"),
            changed_symbols=changed,
        )
        return self._result(
            skill,
            Status.SUCCEEDED if report.allowed else Status.BLOCKED,
            {**report.to_payload(), "benchmarkPlan": [item.to_payload() for item in specs]},
            report.reasons,
            failure_class=None if report.allowed else FailureClass.APPROVAL_REQUIRED,
            evidence={"performanceReportDigest": report.digest},
        )

    # -- Skill 19 --------------------------------------------------------

    def security_preservation(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "candidate_workspace",
                "dependencies_before",
                "dependencies_after",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        candidate_payload = payload.get("candidate_workspace")
        if candidate_payload is not None:
            candidate = snapshot_from_context(
                require_mapping(candidate_payload, "payload.candidate_workspace"),
                approved_root=context.approved_workspace_root,
            )
            patch = diff_snapshots(pipeline.snapshot, candidate)
        else:
            _, transform = self._transform_stage(payload, context, pipeline)
            candidate = transform.snapshot
            patch = transform.patch
        scan = context.resolved_executor.execute(
            ExecutionRequest(
                request_id="security-preservation-scan",
                kind=ExecutionKind.SCAN,
                argv=("security-scan",),
                description="static application security scan for security-preservation",
            )
        )
        report = security.analyse(
            pipeline.snapshot,
            candidate,
            patch,
            dependencies_before=optional_mapping(
                payload.get("dependencies_before"), "payload.dependencies_before"
            )
            or _dependency_map(pipeline.graph),
            dependencies_after=optional_mapping(
                payload.get("dependencies_after"), "payload.dependencies_after"
            ),
            scan_status=scan.status,
        )
        return self._result(
            skill,
            Status.SUCCEEDED if report.allowed else Status.BLOCKED,
            {
                **report.to_payload(),
                "sarif": report.sarif_log(),
                "negativeTests": [dict(item) for item in security.negative_tests(report.findings)],
            },
            report.reasons,
            failure_class=None if report.allowed else FailureClass.APPROVAL_REQUIRED,
            evidence={"securityReportDigest": report.digest},
            risk_class=report.risk_class,
        )

    # -- Skill 21 --------------------------------------------------------

    def multi_repository_refactor_program(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"program_id", "portfolio", "consumer_first", "needs_cleanup", "states", "start_wave"},
            "payload",
        )
        portfolio = program.portfolio_from_payload(
            [
                require_mapping(item, "payload.portfolio[]")
                for item in require_sequence(payload.get("portfolio", ()), "payload.portfolio")
            ]
        )
        plan = program.plan_program(
            require_identifier(payload.get("program_id"), "payload.program_id"),
            portfolio,
            consumer_first=bool(payload.get("consumer_first", False)),
            needs_cleanup=bool(payload.get("needs_cleanup", True)),
        )
        active = program.Program(plan)
        for item in require_sequence(payload.get("states", ()), "payload.states"):
            entry = require_mapping(item, "payload.states[]")
            active.advance(
                require_string(entry.get("repositoryId"), "payload.states[].repositoryId"),
                program.RepositoryState(str(entry.get("state", "pending"))),
                wave_id=str(entry.get("waveId", "")),
                run_id=str(entry.get("runId", "")),
                detail=str(entry.get("detail", "")),
                days_outstanding=int(entry["daysOutstanding"])
                if entry.get("daysOutstanding") is not None
                else None,
            )
        reasons = list(plan.reasons)
        reasons.extend(plan.ordering_violations)
        allowed = plan.executable
        start = optional_string(payload.get("start_wave"), "payload.start_wave")
        gate: dict[str, Any] = {}
        if start:
            may, blockers = active.may_start(start)
            gate = {"wave": start, "mayStart": may, "blockers": list(blockers)}
            allowed = allowed and may
            reasons.extend(blockers)
        return self._result(
            skill,
            Status.SUCCEEDED if allowed else Status.BLOCKED,
            {**active.to_payload(), "startGate": gate},
            reasons,
            failure_class=None if allowed else FailureClass.APPROVAL_REQUIRED,
            evidence={"programPlanDigest": plan.digest},
            risk_class=plan.risk_class,
        )

    # -- Skill 22 --------------------------------------------------------

    def ui_and_client_refactor(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "candidate_workspace",
                "target_platforms",
                "journeys",
                "visual_results",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        candidate_payload = payload.get("candidate_workspace")
        if candidate_payload is not None:
            candidate = snapshot_from_context(
                require_mapping(candidate_payload, "payload.candidate_workspace"),
                approved_root=context.approved_workspace_root,
            )
            patch = diff_snapshots(pipeline.snapshot, candidate)
        else:
            _, transform = self._transform_stage(payload, context, pipeline)
            candidate = transform.snapshot
            patch = transform.patch
        platforms: list[client.Platform] = []
        for name in require_string_sequence(
            payload.get("target_platforms", ("web",)), "payload.target_platforms"
        ):
            try:
                platforms.append(client.Platform(name))
            except ValueError as error:
                raise ContractError(
                    "unsupported_platform",
                    f"'{name}' is not a known client platform",
                    {"supported": [item.value for item in client.Platform]},
                ) from error
        report = client.analyse(
            candidate,
            patch,
            targets=platforms or [client.Platform.WEB],
            journeys=require_string_sequence(payload.get("journeys", ()), "payload.journeys"),
            visual_results=[
                require_mapping(item, "payload.visual_results[]")
                for item in require_sequence(payload.get("visual_results", ()), "payload.visual_results")
            ],
        )
        return self._result(
            skill,
            Status.SUCCEEDED if report.allowed else Status.BLOCKED,
            report.to_payload(),
            report.reasons,
            failure_class=None if report.allowed else FailureClass.APPROVAL_REQUIRED,
            evidence={"clientReportDigest": report.digest},
            risk_class=report.risk_class,
        )

    def _api_diff(self, pipeline: _Pipeline, transform: Any) -> tuple[Any, Any]:
        """Baseline-versus-candidate API surfaces for one transform result."""

        baseline_surface = apicompat.surface_from_files(
            {record.path: record.text or "" for record in pipeline.snapshot}, pipeline.index
        )
        candidate_inventory = discover(transform.snapshot)
        candidate_index = build_index(
            transform.snapshot, candidate_inventory, build_graph(transform.snapshot, candidate_inventory)
        )
        candidate_surface = apicompat.surface_from_files(
            {record.path: record.text or "" for record in transform.snapshot}, candidate_index
        )
        diff = apicompat.diff_surfaces(baseline_surface, candidate_surface)
        decision = apicompat.decide(
            diff,
            public_api_policy=pipeline.request.constraints.public_api_compatibility,
            binary_policy=pipeline.request.constraints.binary_compatibility,
        )
        return diff, decision

    # -- Skill 20 --------------------------------------------------------

    def api_compatibility(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"workspace", "include", "exclude", "request", "explicit_recipes", "allow_draft", "candidate_workspace"},
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        baseline_surface = apicompat.surface_from_files(
            {record.path: record.text or "" for record in pipeline.snapshot}, pipeline.index
        )
        candidate_payload = payload.get("candidate_workspace")
        if candidate_payload is not None:
            candidate_snapshot = snapshot_from_context(
                require_mapping(candidate_payload, "payload.candidate_workspace"),
                approved_root=context.approved_workspace_root,
            )
            candidate_inventory = discover(candidate_snapshot)
            candidate_index = build_index(
                candidate_snapshot, candidate_inventory, build_graph(candidate_snapshot, candidate_inventory)
            )
        else:
            _, transform = self._transform_stage(payload, context, pipeline)
            candidate_snapshot = transform.snapshot
            candidate_inventory = discover(candidate_snapshot)
            candidate_index = build_index(
                candidate_snapshot, candidate_inventory, build_graph(candidate_snapshot, candidate_inventory)
            )
        candidate_surface = apicompat.surface_from_files(
            {record.path: record.text or "" for record in candidate_snapshot}, candidate_index
        )
        diff = apicompat.diff_surfaces(baseline_surface, candidate_surface)
        decision = apicompat.decide(
            diff,
            public_api_policy=pipeline.request.constraints.public_api_compatibility,
            binary_policy=pipeline.request.constraints.binary_compatibility,
        )
        reasons = [
            f"{item.change} {item.identity}: {item.detail}" for item in decision.violations[:20]
        ]
        reasons.extend(decision.required_measures)
        return self._result(
            skill,
            Status.SUCCEEDED if decision.allowed else Status.BLOCKED,
            {
                **apicompat.summarise(diff, decision),
                "consumerMatrix": list(apicompat.consumer_matrix(pipeline.index, baseline_surface)),
            },
            reasons,
            failure_class=None if decision.allowed else FailureClass.APPROVAL_REQUIRED,
            evidence={"apiDiffDigest": diff.digest, "baselineSurfaceDigest": baseline_surface.digest},
            risk_class=decision.risk_class,
        )

    # -- Skill 08 --------------------------------------------------------

    def cross_language_contract_refactor(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "candidate_workspace",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        candidate = self._candidate_stage(payload, context, pipeline)
        before = apicompat.extract_wire_surface(
            {record.path: record.text or "" for record in pipeline.snapshot}
        )
        after = apicompat.extract_wire_surface(
            {record.path: record.text or "" for record in candidate}
        )
        diff = apicompat.diff_surfaces(before, after)
        plan = contractsmig.plan_contract_migration(
            pipeline.snapshot,
            pipeline.index,
            diff,
            compatibility_policy=pipeline.request.constraints.public_api_compatibility,
        )
        if not plan.sources:
            return self._result(
                skill,
                Status.BLOCKED,
                plan.to_payload(),
                (plan.blocked_reason,),
                failure_class=FailureClass.TERMINAL,
            )
        reasons = list(plan.reasons)
        if plan.blocked_reason:
            reasons.insert(0, plan.blocked_reason)
        return self._result(
            skill,
            Status.SUCCEEDED if plan.executable else Status.BLOCKED,
            contractsmig.contract_diff_payload(diff, plan),
            reasons,
            failure_class=None if plan.executable else FailureClass.APPROVAL_REQUIRED,
            evidence={"contractPlanDigest": plan.digest, "wireDiffDigest": diff.digest},
            risk_class=plan.risk_class,
        )

    # -- Skill 09 --------------------------------------------------------

    def data_schema_refactor(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "schema_path",
                "table",
                "old_column",
                "new_column",
                "key_column",
                "dialect",
                "batch_size",
                "strategy",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        schema_path = optional_string(payload.get("schema_path"), "payload.schema_path")
        candidates = (
            [schema_path]
            if schema_path
            else [record.path for record in pipeline.snapshot if record.path.endswith(".sql")]
        )
        tables: dict[str, sqlops.Table] = {}
        for path in candidates:
            record = pipeline.snapshot.get(path)
            if record is None or record.text is None:
                #: An unreadable schema file is *unscanned*, never empty.
                continue
            for table in sqlops.parse_schema(record.text):
                tables.setdefault(table.name, table)
        if not tables:
            return self._result(
                skill,
                Status.BLOCKED,
                {"tables": [], "unscanned": [dict(item) for item in pipeline.inventory.unscanned]},
                (
                    "no CREATE TABLE statement could be parsed from the workspace; "
                    "a schema refactor needs the declared schema, not an inferred one",
                ),
                failure_class=FailureClass.TERMINAL,
            )
        table_name = optional_string(payload.get("table"), "payload.table")
        old_column = optional_string(payload.get("old_column"), "payload.old_column")
        new_column = optional_string(payload.get("new_column"), "payload.new_column")
        if not (table_name and old_column and new_column):
            return self._result(
                skill,
                Status.BLOCKED,
                {
                    "tables": [item.to_payload() for item in tables.values()],
                    "dataAccessPaths": list(
                        sqlops.data_access_paths(
                            {record.path: record.text or "" for record in pipeline.snapshot}
                        )
                    ),
                },
                (
                    "the schema was parsed, but 'table', 'old_column' and 'new_column' are required "
                    "to plan a migration; nothing was inferred on the operator's behalf",
                ),
                failure_class=FailureClass.TERMINAL,
            )
        target = tables.get(table_name) or tables.get(f"public.{table_name}")
        if target is None:
            return self._result(
                skill,
                Status.BLOCKED,
                {"tables": sorted(tables)},
                (f"table '{table_name}' is not declared in the parsed schema",),
                failure_class=FailureClass.TERMINAL,
            )
        dialect_name = optional_string(payload.get("dialect"), "payload.dialect") or "postgresql"
        try:
            dialect = sqlops.Dialect(dialect_name)
        except ValueError as error:
            raise ContractError(
                "unsupported_sql_dialect",
                f"dialect '{dialect_name}' is not supported",
                {"supported": [item.value for item in sqlops.Dialect]},
            ) from error
        plan = sqlops.plan_column_rename(
            target,
            old_column=old_column,
            new_column=new_column,
            key_column=optional_string(payload.get("key_column"), "payload.key_column") or "id",
            dialect=dialect,
            batch_size=integer_value(payload.get("batch_size", 5000), "payload.batch_size", minimum=1),
            strategy=optional_string(payload.get("strategy"), "payload.strategy") or "expand-contract",
        )
        order = sqlops.check_phase_order(plan.files)
        reasons: list[str] = []
        if plan.blocked_reason:
            reasons.append(plan.blocked_reason)
        if not order.ordered:
            reasons.extend(order.violations)
        executable = plan.executable and order.ordered
        return self._result(
            skill,
            Status.SUCCEEDED if executable else Status.BLOCKED,
            {
                **plan.to_payload(),
                "phaseOrder": order.to_payload(),
                "dataValidations": [item.to_payload() for item in sqlops.validation_queries(plan)],
                "dataAccessPaths": list(
                    sqlops.data_access_paths(
                        {record.path: record.text or "" for record in pipeline.snapshot}
                    )
                ),
            },
            reasons,
            failure_class=None if executable else FailureClass.TERMINAL,
            evidence={"schemaPlanDigest": plan.digest},
        )

    # -- Skill 10 --------------------------------------------------------

    def distributed_system_refactor(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "target_service",
                "services",
                "traces",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        declared = [
            require_mapping(item, "payload.services[]")
            for item in require_sequence(payload.get("services", ()), "payload.services")
        ]
        traces = [
            require_mapping(item, "payload.traces[]")
            for item in require_sequence(payload.get("traces", ()), "payload.traces")
        ]
        target = optional_string(payload.get("target_service"), "payload.target_service") or next(
            (item for goal in pipeline.intent.goals for item in goal.targets),
            "the extracted service",
        )
        plan = distributed.plan_distributed_refactor(
            pipeline.snapshot,
            pipeline.index,
            target=target,
            declared_services=declared,
            owners=pipeline.inventory.ownership,
            traces=traces,
        )
        reasons = list(plan.reasons)
        if plan.blocked_reason:
            reasons.insert(0, plan.blocked_reason)
        return self._result(
            skill,
            Status.SUCCEEDED if plan.executable else Status.BLOCKED,
            plan.to_payload(),
            reasons,
            failure_class=None if plan.executable else FailureClass.APPROVAL_REQUIRED,
            evidence={"distributedPlanDigest": plan.digest},
            risk_class=plan.risk_class,
        )

    # -- Skill 11 --------------------------------------------------------

    def test_and_verification(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"workspace", "include", "exclude", "request", "explicit_recipes", "allow_draft", "baseline_profile"},
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        synthesis, transform = self._transform_stage(payload, context, pipeline)
        report = analyse_impact(pipeline.intent, pipeline.index, pipeline.graph, pipeline.inventory)
        baseline = establish_baseline(pipeline.graph, context.resolved_executor)
        cheating = anticheat.analyse(
            transform.patch,
            pipeline.snapshot,
            transform.snapshot,
            test_paths=pipeline.inventory.test_paths,
        )
        languages = [item.language for item in pipeline.inventory.languages if item.language != "unknown"]
        api_diff, compatibility = self._api_diff(pipeline, transform)
        validation = verify(
            transform,
            policy=context.resolved_policy,
            baseline=baseline,
            tests=report.tests,
            graph=pipeline.graph,
            anti_cheat=cheating,
            executor=context.resolved_executor,
            languages=languages[:6],
            risk_class=report.risk.risk_class,
            api_diff=api_diff,
            compatibility=compatibility,
            impact_context={
                "public_api_touched": bool(report.consumers),
                "database_touched": pipeline.request.constraints.database_strategy != "none",
                "security_touched": "authentication" in report.risk.sensitive_areas
                or "authorization" in report.risk.sensitive_areas,
                "performance_sensitive": bool(pipeline.request.constraints.performance_guardrails),
            },
        )
        reasons = [
            f"gate '{item.gate}' failed: {item.detail}"
            for item in validation.gates
            if item.outcome.value == "fail" and item.blocking
        ]
        return self._result(
            skill,
            Status.SUCCEEDED if validation.passed else Status.BLOCKED,
            {
                "validation_report": validation.to_payload(),
                "gate_decisions": [item.to_payload() for item in validation.gates],
                "sarif": validation.sarif(),
                "junit": junit_payload(validation),
                "regression_diff": validation.regressions.to_payload(),
                "recipeLockDigest": synthesis.lock.digest,
            },
            reasons,
            failure_class=None if validation.passed else FailureClass.REPAIRABLE,
            evidence={
                "validationDigest": validation.digest,
                "patchDigest": transform.patch.digest,
                "executor": context.resolved_executor.name,
            },
            risk_class=report.risk.risk_class,
        )

    # -- Skill 12 --------------------------------------------------------

    def bounded_auto_repair(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "failure_output",
                "failures",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        _, transform = self._transform_stage(payload, context, pipeline)
        text = optional_string(payload.get("failure_output"), "payload.failure_output", max_length=1_000_000) or ""
        signatures = list(normalise_failures(text))
        for item in require_sequence(payload.get("failures", ()), "payload.failures"):
            entry = require_mapping(item, "payload.failures[]")
            signatures.extend(normalise_failures(require_string(entry.get("detail"), "payload.failures[].detail")))
        if not signatures:
            return self._result(
                skill,
                Status.SUCCEEDED,
                {
                    "repairAttemptRecords": [],
                    "updatedPatchSet": transform.patch.to_payload(),
                    "unresolvedFailureReport": {"count": 0, "failures": [], "stoppedBecause": ""},
                },
                ("no failure signatures were supplied; there is nothing to repair",),
            )
        budget_spec = pipeline.request.execution.repair_budget
        outcome = repair_failures(
            signatures,
            transform.snapshot,
            pipeline.index,
            budget=budget_from_request(
                budget_spec.max_attempts, budget_spec.max_changed_files, budget_spec.max_cost_usd
            ),
            test_paths=pipeline.inventory.test_paths,
        )
        reasons = [item.reason for item in outcome.attempts if not item.accepted]
        if outcome.stopped_because:
            reasons.append(outcome.stopped_because)
        resolved_all = not outcome.unresolved
        return self._result(
            skill,
            Status.SUCCEEDED if resolved_all else Status.BLOCKED,
            {
                **outcome.to_payload(),
                "attribution": attribute_to_actions(signatures, transform.source_map()),
            },
            reasons,
            failure_class=None if resolved_all else FailureClass.APPROVAL_REQUIRED,
            evidence={"repairPatchDigest": outcome.patch.digest},
        )

    # -- Skill 17 --------------------------------------------------------

    def human_approval_gate(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "gate_id",
                "approvals",
                "requested_by",
                "condition_context",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        synthesis, transform = self._transform_stage(payload, context, pipeline)
        report = analyse_impact(pipeline.intent, pipeline.index, pipeline.graph, pipeline.inventory)
        plan = synthesize_plan(
            pipeline.request,
            context.resolved_policy,
            run_id="approval",
            snapshot_digests={pipeline.snapshot.repository_id: pipeline.snapshot.tree_digest},
            unknown_risk_weight=pipeline.index.coverage.unknown_risk_weight,
        )
        gate_id = optional_string(payload.get("gate_id"), "payload.gate_id") or "gate-transform"
        gate = next((item for item in plan.approval_gates if item.gate_id == gate_id), None)
        roles = gate.roles if gate else ("tech-lead",)
        bound = BoundDigests(
            request=pipeline.request.digest,
            plan=plan.digest,
            recipe_lock=synthesis.lock.digest,
            patch=transform.patch.digest,
        )
        request_record = request_approval(
            run_id="approval",
            gate_id=gate_id,
            roles=roles,
            minimum_approvers=2 if report.risk.risk_class.rank >= RiskClass.R4.rank else 1,
            bound=bound,
            context=build_context(
                run_id="approval",
                gate_id=gate_id,
                goals=pipeline.request.intent.goals,
                risk_class=report.risk.risk_class,
                risk_reasons=report.risk.reasons,
                patch_summary=transform.patch.to_payload(),
                diff_excerpt=transform.patch.render()[:20_000],
                validation_summary={"blockingReasons": list(transform.blocking_reasons)},
                rollback_summary={"strategy": "reverse-patch", "invertible": True},
                alternatives=("run in analyze-only mode and review the plan first",),
            ),
            requested_by=optional_string(payload.get("requested_by"), "payload.requested_by") or "",
            now=context.now,
        )
        records = [
            ApprovalRecord.from_payload(require_mapping(item, "payload.approvals[]"))
            for item in require_sequence(payload.get("approvals", ()), "payload.approvals")
        ]
        verdict = evaluate_approvals(
            request_record,
            records,
            current=bound,
            condition_context=dict(
                optional_mapping(payload.get("condition_context"), "payload.condition_context")
            ),
            now=context.now,
        )
        return self._result(
            skill,
            Status.SUCCEEDED if verdict.satisfied else Status.BLOCKED,
            {
                "approval_request": request_record.to_payload(),
                "approval_decision": verdict.to_payload(),
                "audit_record": audit_record(request_record, records, verdict),
                "conditions": [
                    item.to_payload() for record in records for item in record.conditions
                ],
            },
            verdict.reasons,
            failure_class=None if verdict.satisfied else FailureClass.APPROVAL_REQUIRED,
            evidence={"approvalRequestDigest": request_record.digest},
            risk_class=report.risk.risk_class,
        )

    # -- Skill 13 --------------------------------------------------------

    def canary_rollout(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "rollback_verified",
                "measurements",
                "business_signals_available",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        _, transform = self._transform_stage(payload, context, pipeline)
        report = analyse_impact(pipeline.intent, pipeline.index, pipeline.graph, pipeline.inventory)
        changesets = split_changesets(transform.patch, pipeline.graph, pipeline.inventory)
        plan = plan_rollout(
            risk_class=report.risk.risk_class,
            rollback_verified=bool(payload.get("rollback_verified", False)),
            touches_data=pipeline.request.constraints.database_strategy != "none",
            touches_contracts=bool(report.consumers),
            business_signals_available=bool(payload.get("business_signals_available", False)),
        )
        measurements: dict[str, list[GuardrailReading]] = {}
        for stage_id, readings in optional_mapping(payload.get("measurements"), "payload.measurements").items():
            parsed: list[GuardrailReading] = []
            for item in require_sequence(readings, "payload.measurements[]"):
                entry = require_mapping(item, "payload.measurements[][]")
                parsed.append(
                    GuardrailReading(
                        name=require_string(entry.get("name"), "measurement.name"),
                        baseline=None if entry.get("baseline") is None else Decimal(str(entry["baseline"])),
                        candidate=None if entry.get("candidate") is None else Decimal(str(entry["candidate"])),
                        threshold=None if entry.get("threshold") is None else Decimal(str(entry["threshold"])),
                        higher_is_worse=bool(entry.get("higherIsWorse", True)),
                    )
                )
            measurements[str(stage_id)] = parsed
        reports = run_ladder(plan, measurements)
        final = reports[-1] if reports else None
        succeeded = bool(final and final.decision.value in ("advance", "complete"))
        reasons = [reason for item in reports for reason in item.reasons] if not succeeded else []
        return self._result(
            skill,
            Status.SUCCEEDED if succeeded else Status.BLOCKED,
            release_evidence(changesets, plan, reports).to_payload(),
            reasons,
            failure_class=None if succeeded else FailureClass.APPROVAL_REQUIRED,
            side_effects_performed=False,
            evidence={"rolloutPlanDigest": plan.digest},
            risk_class=report.risk.risk_class,
        )

    # -- Skill 14 --------------------------------------------------------

    def rollback_and_recovery(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {
                "workspace",
                "include",
                "exclude",
                "request",
                "explicit_recipes",
                "allow_draft",
                "events",
                "side_effects",
                "data_reversibility_known",
            },
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        _, transform = self._transform_stage(payload, context, pipeline)
        journal = RunJournal("recovery")
        events = payload.get("events")
        if events is not None:
            journal.replay(
                [require_mapping(item, "payload.events[]") for item in require_sequence(events, "payload.events")]
            )
        else:
            journal.append("run.created", {}, now=context.now)
            journal.write_checkpoint(
                step_id="transform",
                workspace_tree_digest=pipeline.snapshot.tree_digest,
                artifact_manifest_digest=sha256_payload({"artifacts": []}),
                state_version=1,
                now=context.now,
            )
            for item in require_sequence(payload.get("side_effects", ()), "payload.side_effects"):
                entry = require_mapping(item, "payload.side_effects[]")
                journal.record_side_effect(
                    require_string(entry.get("kind"), "side_effect.kind"),
                    require_string(entry.get("target"), "side_effect.target"),
                    idempotency_key=require_string(entry.get("idempotencyKey"), "side_effect.idempotencyKey"),
                    reversible=bool(entry.get("reversible", True)),
                    now=context.now,
                )
            journal.append(
                "step.failed", {"signature": "rollback_required"}, step_id="transform", now=context.now
            )
        checkpoint = last_consistent_checkpoint(
            journal, known_tree_digests=(pipeline.snapshot.tree_digest,), now=context.now
        )
        plan = plan_rollback(
            journal,
            patch=transform.patch,
            checkpoint=checkpoint,
            data_reversibility_known=bool(payload.get("data_reversibility_known", False)),
            risk_class=pipeline.request.risk_floor,
        )
        restored, executed = execute_rollback(
            plan, journal, current=transform.snapshot, patch=transform.patch, now=context.now
        )
        reconciliation = reconcile(journal, checkpoint, restored)
        incident = build_incident_report(journal, plan, reconciliation, executed, now=context.now)
        consistent = reconciliation.consistent and not plan.approval_steps
        return self._result(
            skill,
            Status.SUCCEEDED if consistent else Status.BLOCKED,
            recovery_summary(incident),
            tuple(reconciliation.details)
            + tuple(f"{item.action.value} on '{item.target}' requires approval" for item in plan.approval_steps),
            failure_class=None if consistent else FailureClass.APPROVAL_REQUIRED,
            side_effects_performed=bool(executed),
            evidence={"incidentDigest": incident.digest, "restoredTreeDigest": restored.tree_digest},
        )

    # -- Skill 15 --------------------------------------------------------

    def evidence_and_audit(
        self,
        skill: str,
        payload: Mapping[str, Any],
        context: DispatchContext,
    ) -> HandlerResult:
        reject_unknown_fields(
            payload,
            {"workspace", "include", "exclude", "request", "explicit_recipes", "allow_draft", "signing_key"},
            "payload",
        )
        pipeline = self._pipeline(payload, context)
        synthesis, transform = self._transform_stage(payload, context, pipeline)
        report = analyse_impact(pipeline.intent, pipeline.index, pipeline.graph, pipeline.inventory)
        baseline = establish_baseline(pipeline.graph, context.resolved_executor)
        cheating = anticheat.analyse(
            transform.patch,
            pipeline.snapshot,
            transform.snapshot,
            test_paths=pipeline.inventory.test_paths,
        )
        languages = [item.language for item in pipeline.inventory.languages if item.language != "unknown"]
        validation = verify(
            transform,
            policy=context.resolved_policy,
            baseline=baseline,
            tests=report.tests,
            graph=pipeline.graph,
            anti_cheat=cheating,
            executor=context.resolved_executor,
            languages=languages[:6],
            risk_class=report.risk.risk_class,
        )
        plan = synthesize_plan(
            pipeline.request,
            context.resolved_policy,
            run_id="evidence",
            snapshot_digests={pipeline.snapshot.repository_id: pipeline.snapshot.tree_digest},
        )
        artifacts = [
            artifact_from_payload("refactor-plan", "plan", plan.to_payload()),
            artifact_from_payload("recipes-lock", "recipe-lock", synthesis.lock.to_payload()),
            artifact_from_text("patchset-diff", "patch", transform.patch.render(), media_type="text/x-diff"),
            artifact_from_payload("validation-report", "validation", validation.to_payload()),
            artifact_from_payload("results-sarif", "sarif", validation.sarif()),
            artifact_from_payload("transform-evidence", "transform", transform.evidence.to_payload()),
            artifact_from_payload("impact-report", "impact", report.to_payload()),
        ]
        bundle = assemble(
            run_id="evidence",
            inputs=BundleInputs(
                request_digest=pipeline.request.digest,
                plan_digest=plan.digest,
                policy_digest=context.resolved_policy.digest,
                recipe_lock_digest=synthesis.lock.digest,
                snapshot_digests={pipeline.snapshot.repository_id: pipeline.snapshot.tree_digest},
                adapter_digests=(context.resolved_adapters.digest,),
            ),
            artifacts=artifacts,
            now=context.now,
            source_map=transform.source_map(),
            gate_decisions=[
                GateDecisionRecord(
                    gate=item.gate,
                    decision=item.outcome,
                    evidence_refs=item.evidence_refs,
                )
                for item in validation.gates
            ],
            step_id="transform",
            recipe_execution_id=synthesis.lock.digest,
            validation_refs=(validation.digest,),
            cost=CostBreakdown(wall_clock_seconds=0),
            extra_incomplete_reasons=()
            if validation.passed
            else ("verification did not pass; the bundle documents a failed run",),
        )
        key = optional_string(payload.get("signing_key"), "payload.signing_key", max_length=512)
        if key:
            bundle = sign_bundle(bundle, key_id="host-supplied", secret=key.encode("utf-8"))
        verification = verify_bundle(
            bundle.to_payload(), secret=key.encode("utf-8") if key else None
        )
        complete = bundle.status == "complete" and verification.valid
        return self._result(
            skill,
            Status.SUCCEEDED if complete else Status.BLOCKED,
            {
                "evidence_bundle": bundle.to_payload(),
                "signed_manifest": {
                    "manifestDigest": bundle.manifest_digest,
                    "signed": bundle.signature is not None,
                    "verification": verification.to_payload(),
                },
                "audit_timeline": list(audit_timeline(())),
                "billing_breakdown": billing_breakdown(
                    bundle.cost, changed_files=transform.patch.changed_files, gates_run=len(validation.gates)
                ),
            },
            tuple(bundle.incomplete_reasons) + tuple(verification.reasons),
            failure_class=None if complete else FailureClass.TERMINAL,
            evidence={"bundleDigest": bundle.digest, "manifestDigest": bundle.manifest_digest},
        )


def _autonomy_blockers(
    request: RefactorRequest,
    policy: RefactorPolicy,
    adapters: AdapterCapabilitySnapshot,
) -> tuple[str, ...]:
    """Why autonomous execution is not permitted for this request."""

    blockers: list[str] = []
    autonomy = policy.autonomy
    if request.risk_floor.rank > autonomy.max_risk_class.rank:
        blockers.append(
            f"request risk floor {request.risk_floor.value} exceeds the policy autonomy ceiling "
            f"{autonomy.max_risk_class.value}"
        )
    languages = sorted({"python"})
    below = [
        language
        for language in languages
        if adapters.effective_level(language).rank < autonomy.minimum_adapter_level.rank
    ]
    if below:
        blockers.append(
            "adapter level below the policy minimum "
            f"{autonomy.minimum_adapter_level.value} for: " + ", ".join(below)
        )
    return tuple(blockers)


_DISPATCHER = RuntimeDispatcher()


def dispatch(
    skill_name: str,
    payload: Mapping[str, Any] | None = None,
    *,
    trusted_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispatch one Skill without touching the network, SCM or a shell."""

    context = build_trusted_context(trusted_context)
    return _DISPATCHER.execute(skill_name, payload, context=context).to_dict()


def handler_names() -> tuple[str, ...]:
    return _DISPATCHER.handler_names


def implemented_skills() -> tuple[str, ...]:
    return _DISPATCHER.implemented


__all__ = [
    "PENDING_SKILLS",
    "DispatchContext",
    "RuntimeDispatcher",
    "build_trusted_context",
    "dispatch",
    "handler_names",
    "implemented_skills",
]
