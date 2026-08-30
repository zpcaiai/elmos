"""Normalized runtime traces, conservative equivalence, and replay evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .adapters import AdapterRegistry, AdapterRequest, AdapterResult
from .canonical import digest_object, freeze_json, require_sha256_digest
from .semantic import OperationSpec


class ObservationKind(str, Enum):
    CONTROL_FLOW = "control_flow"
    CALL_STACK = "call_stack"
    STATE = "state"
    VARIABLE = "variable"
    MEMORY = "memory"
    EXCEPTION = "exception"
    API_RESPONSE = "api_response"
    DATABASE_EFFECT = "database_effect"
    TRANSACTION_BOUNDARY = "transaction_boundary"
    MESSAGE_EFFECT = "message_effect"
    FILE_EFFECT = "file_effect"
    CONCURRENCY = "concurrency"


class RuntimeDiffVerdict(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class TraceEvent:
    sequence: int
    kind: ObservationKind
    name: str
    payload: Mapping[str, Any]
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("trace event sequence cannot be negative")
        if not self.name.strip() or len(self.name) > 256:
            raise ValueError("trace event name is required and bounded")
        require_sha256_digest(self.evidence_digest)
        frozen = freeze_json(dict(self.payload))
        if not isinstance(frozen, Mapping):
            raise ValueError("trace event payload must be a JSON object")
        object.__setattr__(self, "payload", frozen)


@dataclass(frozen=True, slots=True)
class RuntimeTrace:
    scenario_id: str
    input_digest: str
    environment_digest: str
    revision_digest: str
    adapter_id: str
    tool_version: str
    events: tuple[TraceEvent, ...]
    required_kinds: tuple[ObservationKind, ...]
    complete: bool
    evidence_digests: tuple[str, ...]
    trace_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.scenario_id.strip() or not self.adapter_id.strip() or not self.tool_version.strip():
            raise ValueError("runtime trace identity, adapter, and tool version are required")
        for digest in (
            self.input_digest,
            self.environment_digest,
            self.revision_digest,
            *self.evidence_digests,
        ):
            require_sha256_digest(digest)
        if not self.required_kinds or len(set(self.required_kinds)) != len(self.required_kinds):
            raise ValueError("runtime trace requires unique observation categories")
        sequences = tuple(item.sequence for item in self.events)
        if sequences != tuple(range(len(self.events))):
            raise ValueError("trace event sequence must be contiguous and ordered from zero")
        body = {
            "scenario_id": self.scenario_id,
            "input_digest": self.input_digest,
            "environment_digest": self.environment_digest,
            "revision_digest": self.revision_digest,
            "adapter_id": self.adapter_id,
            "tool_version": self.tool_version,
            "events": tuple(_event_wire(item) for item in self.events),
            "required_kinds": tuple(item.value for item in self.required_kinds),
            "complete": self.complete,
            "evidence_digests": self.evidence_digests,
        }
        object.__setattr__(
            self, "trace_digest", digest_object(body, domain="runtime-trace")
        )

    @property
    def observed_kinds(self) -> frozenset[ObservationKind]:
        return frozenset(item.kind for item in self.events)

    @property
    def missing_kinds(self) -> tuple[ObservationKind, ...]:
        return tuple(
            item for item in self.required_kinds if item not in self.observed_kinds
        )

    @property
    def evidence_complete(self) -> bool:
        return self.complete and bool(self.evidence_digests) and not self.missing_kinds


@dataclass(frozen=True, slots=True)
class NormalizationRule:
    rule_id: str
    kind: ObservationKind
    field_path: tuple[str, ...]
    action: str
    justification: str
    replacement: Any = None

    def __post_init__(self) -> None:
        if not self.rule_id.strip() or not self.justification.strip():
            raise ValueError("normalization rule identity and justification are required")
        if not self.field_path or any(not item for item in self.field_path):
            raise ValueError("normalization rule field_path is required")
        if self.action not in {"drop", "replace"}:
            raise ValueError("normalization action must be drop or replace")
        object.__setattr__(self, "replacement", freeze_json(self.replacement))


@dataclass(frozen=True, slots=True)
class NormalizationPolicy:
    policy_id: str
    rules: tuple[NormalizationRule, ...] = ()
    authority_evidence_digest: str | None = None
    policy_digest: str = field(init=False)

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("normalization policy_id is required")
        if len({item.rule_id for item in self.rules}) != len(self.rules):
            raise ValueError("normalization rule identities must be unique")
        if self.authority_evidence_digest is not None:
            require_sha256_digest(self.authority_evidence_digest)
        object.__setattr__(
            self,
            "policy_digest",
            digest_object(
                {
                    "policy_id": self.policy_id,
                    "rules": self.rules,
                    "authority_evidence_digest": self.authority_evidence_digest,
                },
                domain="runtime-normalization-policy",
            ),
        )


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    sequence: int
    kind: ObservationKind
    name: str
    payload: Mapping[str, Any]
    event_digest: str
    applied_rules: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NormalizedTrace:
    source_trace_digest: str
    policy_id: str
    policy_digest: str
    normalized_digest: str
    events: tuple[NormalizedEvent, ...]
    complete: bool
    missing_kinds: tuple[ObservationKind, ...]


@dataclass(frozen=True, slots=True)
class TraceDifference:
    kind: ObservationKind | None
    index: int | None
    classification: str
    source_digest: str | None
    target_digest: str | None
    detail: str


@dataclass(frozen=True, slots=True)
class RuntimeDiff:
    verdict: RuntimeDiffVerdict
    source_trace_digest: str
    target_trace_digest: str
    source_normalized_digest: str
    target_normalized_digest: str
    differences: tuple[TraceDifference, ...]
    missing_evidence: tuple[str, ...]
    residual_uncertainty: tuple[str, ...]
    diff_digest: str


@dataclass(frozen=True, slots=True)
class Breakpoint:
    path: str
    line: int
    symbol_identity: str | None = None

    def __post_init__(self) -> None:
        if not self.path.strip() or self.line <= 0:
            raise ValueError("breakpoint path and positive line are required")


@dataclass(frozen=True, slots=True)
class BreakpointPlan:
    scenario_id: str
    breakpoints: tuple[Breakpoint, ...]
    plan_digest: str
    runtime_execution: str = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class RuntimeCounterexample:
    scenario_id: str
    classification: str
    first_difference: TraceDifference
    replay_manifest: Mapping[str, Any]
    counterexample_digest: str
    independently_verified: bool = False


def normalize_trace(
    trace: RuntimeTrace,
    policy: NormalizationPolicy | None = None,
) -> NormalizedTrace:
    policy = policy or NormalizationPolicy("exact-no-normalization")
    normalized: list[NormalizedEvent] = []
    for event in trace.events:
        payload: Any = _mutable_json(event.payload)
        applied: list[str] = []
        for rule in policy.rules:
            if rule.kind is not event.kind:
                continue
            changed = _apply_rule(payload, rule)
            if changed:
                applied.append(rule.rule_id)
        frozen = freeze_json(payload)
        if not isinstance(frozen, Mapping):
            raise RuntimeError("normalized event payload stopped being an object")
        event_digest = digest_object(
            {
                "sequence": event.sequence,
                "kind": event.kind.value,
                "name": event.name,
                "payload": frozen,
                "applied_rules": tuple(applied),
            },
            domain="normalized-runtime-event",
        )
        normalized.append(
            NormalizedEvent(
                event.sequence,
                event.kind,
                event.name,
                frozen,
                event_digest,
                tuple(applied),
            )
        )
    normalized_digest = digest_object(
        {
            "source_trace_digest": trace.trace_digest,
            "policy_id": policy.policy_id,
            "policy_digest": policy.policy_digest,
            "events": tuple(item.event_digest for item in normalized),
            "complete": trace.evidence_complete,
            "missing_kinds": tuple(item.value for item in trace.missing_kinds),
        },
        domain="normalized-runtime-trace",
    )
    return NormalizedTrace(
        source_trace_digest=trace.trace_digest,
        policy_id=policy.policy_id,
        policy_digest=policy.policy_digest,
        normalized_digest=normalized_digest,
        events=tuple(normalized),
        complete=trace.evidence_complete,
        missing_kinds=trace.missing_kinds,
    )


def compare_runtime_traces(
    source: RuntimeTrace,
    target: RuntimeTrace,
    *,
    policy: NormalizationPolicy | None = None,
    only_kind: ObservationKind | None = None,
    require_same_revision: bool = False,
) -> RuntimeDiff:
    source_normalized = normalize_trace(source, policy)
    target_normalized = normalize_trace(target, policy)
    differences: list[TraceDifference] = []
    missing: list[str] = []
    residual: list[str] = []
    if source.scenario_id != target.scenario_id:
        differences.append(
            TraceDifference(None, None, "environment_difference", None, None, "scenario identifiers differ")
        )
    if source.input_digest != target.input_digest:
        differences.append(
            TraceDifference(None, None, "environment_difference", source.input_digest, target.input_digest, "scenario input digests differ")
        )
    if source.environment_digest != target.environment_digest:
        differences.append(
            TraceDifference(None, None, "environment_difference", source.environment_digest, target.environment_digest, "environment contract digests differ")
        )
    if require_same_revision and source.revision_digest != target.revision_digest:
        differences.append(
            TraceDifference(
                None,
                None,
                "environment_difference",
                source.revision_digest,
                target.revision_digest,
                "deterministic replay revision digests differ",
            )
        )
    source_events = tuple(
        item for item in source_normalized.events if only_kind is None or item.kind is only_kind
    )
    target_events = tuple(
        item for item in target_normalized.events if only_kind is None or item.kind is only_kind
    )
    maximum = max(len(source_events), len(target_events))
    for index in range(maximum):
        left = source_events[index] if index < len(source_events) else None
        right = target_events[index] if index < len(target_events) else None
        if left is not None and right is not None and left.event_digest == right.event_digest:
            continue
        kind = left.kind if left is not None else right.kind if right is not None else only_kind
        differences.append(
            TraceDifference(
                kind,
                index,
                "semantic_regression",
                left.event_digest if left else None,
                right.event_digest if right else None,
                "normalized observation differs" if left and right else "normalized observation is missing on one side",
            )
        )
    for label, normalized in (("source", source_normalized), ("target", target_normalized)):
        if not normalized.complete:
            missing.append(f"{label}: trace completeness/evidence")
        for kind in normalized.missing_kinds:
            if only_kind is None or kind is only_kind:
                missing.append(f"{label}: {kind.value}")
    if policy and policy.rules and policy.authority_evidence_digest is None:
        missing.append("normalization policy: authority evidence")
    if only_kind is not None:
        if only_kind not in source.observed_kinds:
            missing.append(f"source: {only_kind.value}")
        if only_kind not in target.observed_kinds:
            missing.append(f"target: {only_kind.value}")
    environment_differences = any(
        item.classification == "environment_difference" for item in differences
    )
    semantic_differences = any(
        item.classification == "semantic_regression" for item in differences
    )
    if semantic_differences:
        verdict = RuntimeDiffVerdict.FAIL
    elif missing or environment_differences:
        verdict = RuntimeDiffVerdict.INSUFFICIENT_EVIDENCE
    else:
        verdict = RuntimeDiffVerdict.PASS
    if policy and policy.rules:
        residual.extend(
            f"normalization:{item.rule_id}:{item.justification}" for item in policy.rules
        )
    diff_digest = digest_object(
        {
            "verdict": verdict.value,
            "source_trace_digest": source.trace_digest,
            "target_trace_digest": target.trace_digest,
            "source_normalized_digest": source_normalized.normalized_digest,
            "target_normalized_digest": target_normalized.normalized_digest,
            "differences": tuple(_difference_wire(item) for item in differences),
            "missing_evidence": tuple(sorted(set(missing))),
            "residual_uncertainty": tuple(residual),
            "only_kind": only_kind.value if only_kind else None,
            "require_same_revision": require_same_revision,
        },
        domain="runtime-diff",
    )
    return RuntimeDiff(
        verdict=verdict,
        source_trace_digest=source.trace_digest,
        target_trace_digest=target.trace_digest,
        source_normalized_digest=source_normalized.normalized_digest,
        target_normalized_digest=target_normalized.normalized_digest,
        differences=tuple(differences),
        missing_evidence=tuple(sorted(set(missing))),
        residual_uncertainty=tuple(residual),
        diff_digest=diff_digest,
    )


class RuntimeProofService:
    """Exact K3 operation router backed only by explicitly registered DAP adapters."""

    def __init__(self, adapters: AdapterRegistry | None = None) -> None:
        self.adapters = adapters or AdapterRegistry()

    def execute(self, operation: str, **kwargs: Any) -> Any:
        spec = K3_OPERATION_SPECS.get(operation)
        if spec is None:
            raise KeyError(f"unknown K3 operation: {operation}")
        return getattr(self, spec.method)(**kwargs)

    def dap_adapter_discovery(self) -> Mapping[str, Any]:
        return self.adapters.discovery("dap")

    def dap_runtime_driver(self, request: AdapterRequest) -> AdapterResult:
        _require_dap(request)
        return self.adapters.invoke(request)

    @staticmethod
    def breakpoint_plan_generator(
        scenario_id: str, breakpoints: Sequence[Breakpoint]
    ) -> BreakpointPlan:
        values = tuple(breakpoints)
        if not scenario_id.strip() or not values:
            raise ValueError("scenario and at least one breakpoint are required")
        digest = digest_object(
            {
                "scenario_id": scenario_id,
                "breakpoints": tuple(
                    (item.path, item.line, item.symbol_identity) for item in values
                ),
                "runtime_execution": "NOT_RUN",
            },
            domain="breakpoint-plan",
        )
        return BreakpointPlan(scenario_id, values, digest)

    @staticmethod
    def runtime_state_capture(trace: RuntimeTrace) -> tuple[TraceEvent, ...]:
        return _capture(trace, {ObservationKind.STATE})

    @staticmethod
    def call_stack_capture(trace: RuntimeTrace) -> tuple[TraceEvent, ...]:
        return _capture(trace, {ObservationKind.CALL_STACK, ObservationKind.CONTROL_FLOW})

    @staticmethod
    def variable_snapshot(trace: RuntimeTrace) -> tuple[TraceEvent, ...]:
        return _capture(trace, {ObservationKind.VARIABLE})

    @staticmethod
    def exception_trace(trace: RuntimeTrace) -> tuple[TraceEvent, ...]:
        return _capture(trace, {ObservationKind.EXCEPTION})

    @staticmethod
    def memory_state_probe(trace: RuntimeTrace) -> tuple[TraceEvent, ...]:
        return _capture(trace, {ObservationKind.MEMORY})

    @staticmethod
    def differential_debugger(
        source: RuntimeTrace,
        target: RuntimeTrace,
        policy: NormalizationPolicy | None = None,
    ) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy)

    @staticmethod
    def control_flow_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.CONTROL_FLOW)

    @staticmethod
    def state_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.STATE)

    @staticmethod
    def exception_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.EXCEPTION)

    @staticmethod
    def api_response_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.API_RESPONSE)

    @staticmethod
    def database_effect_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.DATABASE_EFFECT)

    @staticmethod
    def transaction_boundary_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.TRANSACTION_BOUNDARY)

    @staticmethod
    def message_effect_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.MESSAGE_EFFECT)

    @staticmethod
    def file_effect_equivalence(source: RuntimeTrace, target: RuntimeTrace, policy: NormalizationPolicy | None = None) -> RuntimeDiff:
        return compare_runtime_traces(source, target, policy=policy, only_kind=ObservationKind.FILE_EFFECT)

    @staticmethod
    def concurrency_observation(trace: RuntimeTrace) -> tuple[TraceEvent, ...]:
        return _capture(trace, {ObservationKind.CONCURRENCY})

    @staticmethod
    def deterministic_replay(
        original: RuntimeTrace,
        replayed: RuntimeTrace,
        policy: NormalizationPolicy | None = None,
    ) -> RuntimeDiff:
        return compare_runtime_traces(
            original, replayed, policy=policy, require_same_revision=True
        )

    @staticmethod
    def scenario_replay(
        original: RuntimeTrace,
        replayed: RuntimeTrace,
        policy: NormalizationPolicy | None = None,
    ) -> RuntimeDiff:
        return compare_runtime_traces(
            original, replayed, policy=policy, require_same_revision=True
        )

    def fault_injection_runner(self, request: AdapterRequest) -> AdapterResult:
        _require_dap(request)
        return self.adapters.invoke(request)

    @staticmethod
    def counterexample_generator(diff: RuntimeDiff, scenario_id: str) -> RuntimeCounterexample | None:
        if diff.verdict is RuntimeDiffVerdict.PASS or not diff.differences:
            return None
        first = diff.differences[0]
        replay_manifest = MappingProxyType(
            {
                "scenario_id": scenario_id,
                "source_trace_digest": diff.source_trace_digest,
                "target_trace_digest": diff.target_trace_digest,
                "diff_digest": diff.diff_digest,
                "first_difference_index": first.index,
                "deterministic_input_required": True,
                "runtime_execution": "NOT_RUN",
            }
        )
        counterexample_digest = digest_object(
            {
                "scenario_id": scenario_id,
                "classification": first.classification,
                "first_difference": _difference_wire(first),
                "replay_manifest": replay_manifest,
            },
            domain="runtime-counterexample",
        )
        return RuntimeCounterexample(
            scenario_id,
            first.classification,
            first,
            replay_manifest,
            counterexample_digest,
        )

    @staticmethod
    def runtime_root_cause_localizer(diff: RuntimeDiff) -> Mapping[str, Any]:
        first = diff.differences[0] if diff.differences else None
        status = "LOCALIZED" if first is not None else "INSUFFICIENT_EVIDENCE"
        payload = {
            "status": status,
            "diff_digest": diff.diff_digest,
            "first_difference": _difference_wire(first) if first else None,
            "causal_proof": "NOT_RUN",
        }
        return MappingProxyType(
            {
                **payload,
                "localization_digest": digest_object(
                    payload, domain="runtime-root-cause"
                ),
            }
        )

    def auto_debug_repair_loop(
        self, diff: RuntimeDiff, request: AdapterRequest
    ) -> Mapping[str, Any] | AdapterResult:
        if diff.verdict is not RuntimeDiffVerdict.FAIL:
            payload = {
                "status": "INSUFFICIENT_EVIDENCE",
                "reason": "repair requires a concrete failing runtime difference",
                "diff_digest": diff.diff_digest,
                "mutation_performed": False,
            }
            return MappingProxyType(
                {
                    **payload,
                    "result_digest": digest_object(
                        payload, domain="auto-debug-repair"
                    ),
                }
            )
        _require_dap(request)
        return self.adapters.invoke(request)


def _capture(trace: RuntimeTrace, kinds: set[ObservationKind]) -> tuple[TraceEvent, ...]:
    return tuple(item for item in trace.events if item.kind in kinds)


def _event_wire(event: TraceEvent) -> Mapping[str, Any]:
    return {
        "sequence": event.sequence,
        "kind": event.kind.value,
        "name": event.name,
        "payload": event.payload,
        "evidence_digest": event.evidence_digest,
    }


def _difference_wire(difference: TraceDifference | None) -> Mapping[str, Any] | None:
    if difference is None:
        return None
    return {
        "kind": difference.kind.value if difference.kind else None,
        "index": difference.index,
        "classification": difference.classification,
        "source_digest": difference.source_digest,
        "target_digest": difference.target_digest,
        "detail": difference.detail,
    }


def _mutable_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _mutable_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mutable_json(item) for item in value]
    return value


def _apply_rule(payload: Any, rule: NormalizationRule) -> bool:
    current = payload
    for component in rule.field_path[:-1]:
        if not isinstance(current, dict) or component not in current:
            return False
        current = current[component]
    leaf = rule.field_path[-1]
    if not isinstance(current, dict) or leaf not in current:
        return False
    if rule.action == "drop":
        del current[leaf]
    else:
        current[leaf] = _mutable_json(freeze_json(rule.replacement))
    return True


def _require_dap(request: AdapterRequest) -> None:
    if request.protocol != "dap":
        raise ValueError("runtime proof operation requires dap adapter protocol")


K3_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {
        "dap-adapter-discovery": OperationSpec("dap-adapter-discovery", "K3", "dap_adapter_discovery", "AdapterDiscovery", True),
        "dap-runtime-driver": OperationSpec("dap-runtime-driver", "K3", "dap_runtime_driver", "AdapterResult", True),
        "breakpoint-plan-generator": OperationSpec("breakpoint-plan-generator", "K3", "breakpoint_plan_generator", "BreakpointPlan"),
        "runtime-state-capture": OperationSpec("runtime-state-capture", "K3", "runtime_state_capture", "TraceEvent[]"),
        "call-stack-capture": OperationSpec("call-stack-capture", "K3", "call_stack_capture", "TraceEvent[]"),
        "variable-snapshot": OperationSpec("variable-snapshot", "K3", "variable_snapshot", "TraceEvent[]"),
        "exception-trace": OperationSpec("exception-trace", "K3", "exception_trace", "TraceEvent[]"),
        "memory-state-probe": OperationSpec("memory-state-probe", "K3", "memory_state_probe", "TraceEvent[]"),
        "differential-debugger": OperationSpec("differential-debugger", "K3", "differential_debugger", "RuntimeDiff"),
        "control-flow-equivalence": OperationSpec("control-flow-equivalence", "K3", "control_flow_equivalence", "RuntimeDiff"),
        "state-equivalence": OperationSpec("state-equivalence", "K3", "state_equivalence", "RuntimeDiff"),
        "exception-equivalence": OperationSpec("exception-equivalence", "K3", "exception_equivalence", "RuntimeDiff"),
        "api-response-equivalence": OperationSpec("api-response-equivalence", "K3", "api_response_equivalence", "RuntimeDiff"),
        "database-effect-equivalence": OperationSpec("database-effect-equivalence", "K3", "database_effect_equivalence", "RuntimeDiff"),
        "transaction-boundary-equivalence": OperationSpec("transaction-boundary-equivalence", "K3", "transaction_boundary_equivalence", "RuntimeDiff"),
        "message-effect-equivalence": OperationSpec("message-effect-equivalence", "K3", "message_effect_equivalence", "RuntimeDiff"),
        "file-effect-equivalence": OperationSpec("file-effect-equivalence", "K3", "file_effect_equivalence", "RuntimeDiff"),
        "concurrency-observation": OperationSpec("concurrency-observation", "K3", "concurrency_observation", "TraceEvent[]"),
        "deterministic-replay": OperationSpec("deterministic-replay", "K3", "deterministic_replay", "RuntimeDiff"),
        "scenario-replay": OperationSpec("scenario-replay", "K3", "scenario_replay", "RuntimeDiff"),
        "fault-injection-runner": OperationSpec("fault-injection-runner", "K3", "fault_injection_runner", "AdapterResult", True),
        "counterexample-generator": OperationSpec("counterexample-generator", "K3", "counterexample_generator", "RuntimeCounterexample"),
        "runtime-root-cause-localizer": OperationSpec("runtime-root-cause-localizer", "K3", "runtime_root_cause_localizer", "RootCauseLocalization"),
        "auto-debug-repair-loop": OperationSpec("auto-debug-repair-loop", "K3", "auto_debug_repair_loop", "AdapterResult", True),
    }
)


if len(K3_OPERATION_SPECS) != 24:
    raise RuntimeError("K3 operation bindings drifted from the source catalog")


__all__ = [
    "Breakpoint",
    "BreakpointPlan",
    "K3_OPERATION_SPECS",
    "NormalizationPolicy",
    "NormalizationRule",
    "NormalizedEvent",
    "NormalizedTrace",
    "ObservationKind",
    "RuntimeCounterexample",
    "RuntimeDiff",
    "RuntimeDiffVerdict",
    "RuntimeProofService",
    "RuntimeTrace",
    "TraceDifference",
    "TraceEvent",
    "compare_runtime_traces",
    "normalize_trace",
]
