"""Kernel domain models, data contracts, and verification logic for AI Capability Enhancement."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

# ---------------------------------------------------------------------------
# 1. Capability Negotiation & Target Profiles
# ---------------------------------------------------------------------------

ALLOWED_STATUSES = {
    "supported", "conditional", "emulated", "external-runtime",
    "external-policy", "unsupported", "blocked",
}


@dataclass(frozen=True)
class FeatureRequirement:
    name: str
    critical: bool = True
    accepted_statuses: frozenset[str] = frozenset(
        {"supported", "conditional", "external-runtime", "external-policy"}
    )


@dataclass(frozen=True)
class TargetProfile:
    target: str
    features: Mapping[str, str]
    exact_version: str
    adapter_digest: str


@dataclass(frozen=True)
class FeatureDecision:
    requirement: str
    target: str
    status: str
    critical: bool
    obligations: tuple[str, ...] = ()


@dataclass(frozen=True)
class TargetDecision:
    target: str
    overall: str
    decisions: tuple[FeatureDecision, ...]


@dataclass(frozen=True)
class NegotiationResult:
    overall: str
    targets: tuple[TargetDecision, ...]
    blocked_reasons: tuple[str, ...] = ()


def _obligations(status: str, feature: str) -> tuple[str, ...]:
    if status == "supported":
        return (f"native-conformance:{feature}",)
    if status == "conditional":
        return (f"condition-proof:{feature}", f"native-conformance:{feature}")
    if status == "emulated":
        return (f"emulation-equivalence:{feature}", f"performance-bound:{feature}")
    if status == "external-runtime":
        return (f"runtime-integration:{feature}", f"failure-recovery:{feature}")
    if status == "external-policy":
        return (f"policy-enforcement:{feature}", f"negative-policy-test:{feature}")
    return (f"blocked-capability:{feature}",)


def negotiate(
    requirements: Sequence[FeatureRequirement],
    profiles: Sequence[TargetProfile],
) -> NegotiationResult:
    if not requirements:
        raise ValueError("at least one requirement is required")
    if not profiles:
        return NegotiationResult("BLOCKED", (), ("no target profiles",))

    target_results: list[TargetDecision] = []
    global_reasons: list[str] = []
    for profile in profiles:
        if not profile.exact_version or not profile.adapter_digest.startswith("sha256:"):
            target_results.append(TargetDecision(
                profile.target, "BLOCKED", tuple(
                    FeatureDecision(r.name, profile.target, "blocked", r.critical,
                                    ("release-pin-missing",)) for r in requirements
                )
            ))
            global_reasons.append(f"{profile.target}: exact version or adapter digest missing")
            continue

        decisions: list[FeatureDecision] = []
        target_blocked = False
        target_bounded = False
        for req in requirements:
            status = profile.features.get(req.name, "unsupported")
            if status not in ALLOWED_STATUSES:
                status = "blocked"
            if req.critical and status not in req.accepted_statuses:
                target_blocked = True
            elif status != "supported":
                target_bounded = True
            decisions.append(FeatureDecision(
                req.name, profile.target, status, req.critical, _obligations(status, req.name)
            ))
        overall = "BLOCKED" if target_blocked else ("BOUNDED" if target_bounded else "SUPPORTED")
        target_results.append(TargetDecision(profile.target, overall, tuple(decisions)))

    if all(t.overall == "BLOCKED" for t in target_results):
        overall = "BLOCKED"
        if not global_reasons:
            global_reasons.append("every target blocks at least one critical requirement")
    elif any(t.overall == "SUPPORTED" for t in target_results):
        overall = "SUPPORTED"
    else:
        overall = "BOUNDED"

    return NegotiationResult(overall, tuple(target_results), tuple(global_reasons))


# ---------------------------------------------------------------------------
# 2. Trace Equivalence & Validation
# ---------------------------------------------------------------------------

def validate_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    events = trace.get("events", [])
    seen_ids = set()
    for idx, event in enumerate(events):
        eid = event.get("id")
        if not eid or eid in seen_ids:
            return {"valid": False, "error": f"event {idx} has missing or duplicate id"}
        seen_ids.add(eid)
        if "kind" not in event or "timestamp" not in event:
            return {"valid": False, "error": f"event {eid} missing kind or timestamp"}
        if event.get("cause") and event.get("cause") not in seen_ids and event.get("cause") != eid:
            return {"valid": False, "error": f"event {eid} references unknown cause {event.get('cause')}"}
    return {"valid": True, "eventCount": len(events)}


def compare_traces(ref: Mapping[str, Any], cand: Mapping[str, Any]) -> dict[str, Any]:
    vr = validate_trace(ref)
    if not vr["valid"]:
        return {"equivalent": False, "error": f"reference invalid: {vr['error']}"}
    vc = validate_trace(cand)
    if not vc["valid"]:
        return {"equivalent": False, "error": f"candidate invalid: {vc['error']}"}

    ref_effects = [e for e in ref.get("events", []) if e.get("is_side_effect", False) or e.get("kind") in ("state_write", "tool_call", "network_egress")]
    cand_effects = [e for e in cand.get("events", []) if e.get("is_side_effect", False) or e.get("kind") in ("state_write", "tool_call", "network_egress")]

    if len(ref_effects) != len(cand_effects):
        return {
            "equivalent": False,
            "mismatch": "side_effect_count",
            "refCount": len(ref_effects),
            "candCount": len(cand_effects),
        }

    for idx, (r, c) in enumerate(zip(ref_effects, cand_effects)):
        if r.get("kind") != c.get("kind"):
            return {"equivalent": False, "mismatch": f"effect_{idx}_kind", "ref": r.get("kind"), "cand": c.get("kind")}
        if r.get("target") != c.get("target"):
            return {"equivalent": False, "mismatch": f"effect_{idx}_target", "ref": r.get("target"), "cand": c.get("target")}
        if r.get("payload_hash") != c.get("payload_hash"):
            return {"equivalent": False, "mismatch": f"effect_{idx}_payload", "ref": r.get("payload_hash"), "cand": c.get("payload_hash")}

    return {"equivalent": True, "sideEffectsCount": len(ref_effects)}


# ---------------------------------------------------------------------------
# 3. Certifier & Decision Governance
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProofResult:
    obligation_id: str
    status: str  # PROVED, DISPROVED, UNKNOWN, TIMEOUT
    evidence_digest: str
    severity: str = "critical"


@dataclass(frozen=True)
class CertificationInput:
    goal_id: str
    target: str
    results: Sequence[ProofResult]
    residual_risk_accepted: bool = False


@dataclass(frozen=True)
class CertificationDecision:
    status: str  # CERTIFIED, NOT_CERTIFIED, BLOCKED
    certified_level: str  # E0-E5, NONE
    reasons: tuple[str, ...] = ()


def certify(inp: CertificationInput) -> CertificationDecision:
    if not inp.results:
        return CertificationDecision("BLOCKED", "NONE", ("no proof results provided",))

    critical_unknowns = [r for r in inp.results if r.severity == "critical" and r.status in ("UNKNOWN", "TIMEOUT", "DISPROVED")]
    if critical_unknowns:
        return CertificationDecision("BLOCKED", "NONE", (f"critical obligations failed: {[r.obligation_id for r in critical_unknowns]}",))

    any_disproved = any(r.status == "DISPROVED" for r in inp.results)
    if any_disproved:
        return CertificationDecision("NOT_CERTIFIED", "NONE", ("non-critical proof obligations disproved",))

    all_proved = all(r.status == "PROVED" for r in inp.results)
    if all_proved:
        return CertificationDecision("CERTIFIED", "E3", ("all obligations proved locally",))

    return CertificationDecision("NOT_CERTIFIED", "NONE", ("some obligations unresolved without waiver",))


# ---------------------------------------------------------------------------
# 4. Skill IR & Portability
# ---------------------------------------------------------------------------

def validate_skill_ir(skill_ir: Mapping[str, Any]) -> dict[str, Any]:
    name = skill_ir.get("name")
    if not name or not isinstance(name, str):
        return {"valid": False, "error": "skill name is required"}
    tools = skill_ir.get("tools", [])
    for t in tools:
        if ".." in t or "/" in t or "\\" in t:
            return {"valid": False, "error": f"path traversal in tool name {t}"}
    return {"valid": True, "name": name}


def permission_expansions(source_perms: Sequence[str], target_perms: Sequence[str]) -> list[str]:
    s_set = set(source_perms)
    return [p for p in target_perms if p not in s_set]


def portability_decision(source_ir: Mapping[str, Any], target_ir: Mapping[str, Any]) -> dict[str, Any]:
    sv = validate_skill_ir(source_ir)
    if not sv["valid"]:
        return {"portable": False, "reason": sv["error"]}
    tv = validate_skill_ir(target_ir)
    if not tv["valid"]:
        return {"portable": False, "reason": tv["error"]}

    expansions = permission_expansions(source_ir.get("permissions", []), target_ir.get("permissions", []))
    if expansions:
        return {"portable": False, "reason": f"permission expansion detected: {expansions}"}

    missing_tools = [t for t in source_ir.get("tools", []) if t not in target_ir.get("tools", [])]
    if missing_tools:
        return {"portable": False, "reason": f"critical tool dropped: {missing_tools}"}

    return {"portable": True}


# ---------------------------------------------------------------------------
# 5. Trigger Evaluation & Activation Gate
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TriggerObservation:
    skill_name: str
    should_activate: bool
    did_activate: bool


@dataclass(frozen=True)
class TriggerMetrics:
    precision: float
    recall: float
    f1: float
    total: int


def evaluate_trigger(observations: Sequence[TriggerObservation]) -> TriggerMetrics:
    if not observations:
        return TriggerMetrics(0.0, 0.0, 0.0, 0)
    tp = sum(1 for o in observations if o.should_activate and o.did_activate)
    fp = sum(1 for o in observations if not o.should_activate and o.did_activate)
    fn = sum(1 for o in observations if o.should_activate and not o.did_activate)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return TriggerMetrics(precision, recall, f1, len(observations))


def trigger_gate(metrics: TriggerMetrics, min_f1: float = 0.85, min_precision: float = 0.90) -> bool:
    if metrics.total == 0:
        return False
    return metrics.f1 >= min_f1 and metrics.precision >= min_precision


# ---------------------------------------------------------------------------
# 6. MCP Tasks & Durable Bridge
# ---------------------------------------------------------------------------

@dataclass
class TaskState:
    task_id: str
    status: str  # INITIALIZED, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED
    result: Any = None
    error: str | None = None
    checkpoints: list[str] = field(default_factory=list)


class McpTaskBridge:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskState] = {}

    def create_task(self, task_id: str) -> TaskState:
        if task_id in self._tasks:
            raise ValueError(f"task {task_id} already exists")
        state = TaskState(task_id, "INITIALIZED")
        self._tasks[task_id] = state
        return state

    def checkpoint(self, task_id: str, data: str) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"task {task_id} not found")
        self._tasks[task_id].checkpoints.append(data)

    def complete(self, task_id: str, result: Any) -> None:
        if task_id not in self._tasks:
            raise KeyError(f"task {task_id} not found")
        self._tasks[task_id].status = "COMPLETED"
        self._tasks[task_id].result = result

    def get_state(self, task_id: str) -> TaskState:
        return self._tasks[task_id]


# ---------------------------------------------------------------------------
# 7. Judge Calibration & Runaway Guard
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Calibration:
    judge_model: str
    correlation: float
    ece: float  # Expected Calibration Error
    sample_size: int


def calibrate(predictions: Sequence[float], ground_truth: Sequence[float], model: str = "judge-v1") -> Calibration:
    if not predictions or len(predictions) != len(ground_truth):
        return Calibration(model, 0.0, 1.0, 0)
    n = len(predictions)
    error_sum = sum(abs(p - g) for p, g in zip(predictions, ground_truth))
    ece = error_sum / n
    corr = 1.0 - min(1.0, ece)
    return Calibration(model, corr, ece, n)


def judge_use_decision(cal: Calibration, max_ece: float = 0.15, min_samples: int = 20) -> dict[str, Any]:
    if cal.sample_size < min_samples:
        return {"allowed": False, "reason": "insufficient sample size"}
    if cal.ece > max_ece:
        return {"allowed": False, "reason": f"ECE {cal.ece:.3f} exceeds threshold {max_ece}"}
    return {"allowed": True, "calibration": cal}


@dataclass(frozen=True)
class BudgetLimit:
    max_steps: int = 50
    max_tokens: int = 100_000
    max_cost_usd: float = 5.00


class RunawayGuard:
    def __init__(self, budget: BudgetLimit) -> None:
        self.budget = budget
        self.steps = 0
        self.tokens = 0
        self.cost = 0.0

    def step(self, tokens: int = 0, cost: float = 0.0) -> None:
        self.steps += 1
        self.tokens += tokens
        self.cost += cost
        if self.steps > self.budget.max_steps:
            raise RuntimeError(f"runaway detected: step limit {self.budget.max_steps} exceeded")
        if self.tokens > self.budget.max_tokens:
            raise RuntimeError(f"runaway detected: token limit {self.budget.max_tokens} exceeded")
        if self.cost > self.budget.max_cost_usd:
            raise RuntimeError(f"runaway detected: budget limit ${self.budget.max_cost_usd} exceeded")


# ---------------------------------------------------------------------------
# 8. Schema Evolution & Fingerprinting
# ---------------------------------------------------------------------------

def backward_compatibility(old_schema: Mapping[str, Any], new_schema: Mapping[str, Any]) -> dict[str, Any]:
    old_req = set(old_schema.get("required", []))
    new_req = set(new_schema.get("required", []))

    added_required = new_req - old_req
    if added_required:
        return {"compatible": False, "reason": f"new required fields added: {sorted(added_required)}"}

    old_props = old_schema.get("properties", {})
    new_props = new_schema.get("properties", {})
    for k, v in old_props.items():
        if k in new_props:
            if v.get("type") != new_props[k].get("type"):
                return {"compatible": False, "reason": f"type changed for property {k}"}

    return {"compatible": True}


def evolution_decision(old_s: Mapping[str, Any], new_s: Mapping[str, Any], migration_plan_present: bool = False) -> str:
    res = backward_compatibility(old_s, new_s)
    if res["compatible"]:
        return "APPLY_DIRECT"
    if migration_plan_present:
        return "APPLY_WITH_MIGRATION"
    return "BLOCKED"


def compare_fingerprints(fp1: Mapping[str, str], fp2: Mapping[str, str]) -> dict[str, Any]:
    diffs = {}
    for k, v in fp1.items():
        if fp2.get(k) != v:
            diffs[k] = {"before": v, "after": fp2.get(k)}
    for k, v in fp2.items():
        if k not in fp1:
            diffs[k] = {"before": None, "after": v}
    return {"identical": len(diffs) == 0, "differences": diffs}


def recertification_decision(fp_diff: Mapping[str, Any]) -> str:
    if fp_diff.get("identical"):
        return "REUSE_CERTIFICATE"
    diffs = fp_diff.get("differences", {})
    critical_keys = {"model_version", "tool_schema_hash", "policy_hash", "adapter_digest"}
    if any(k in diffs for k in critical_keys):
        return "FULL_RECERTIFICATION"
    return "INCREMENTAL_EVAL"


# ---------------------------------------------------------------------------
# 9. RAG Security & Tenant Memory
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalCandidate:
    doc_id: str
    tenant_id: str
    acl: frozenset[str]
    is_deleted: bool = False


def authorize_candidates(candidates: Sequence[RetrievalCandidate], request_tenant: str, user_roles: frozenset[str]) -> list[RetrievalCandidate]:
    authorized = []
    for c in candidates:
        if c.is_deleted:
            continue
        if c.tenant_id != request_tenant:
            continue
        if c.acl and not (c.acl & user_roles):
            continue
        authorized.append(c)
    return authorized


def deletion_reconciled(doc_id: str, index_state: Sequence[str], tombstone_log: Sequence[str]) -> bool:
    if doc_id in tombstone_log and doc_id in index_state:
        return False
    return True


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    tenant_id: str
    content: str
    tags: frozenset[str] = frozenset()


def authorize_memory(records: Sequence[MemoryRecord], tenant_id: str) -> list[MemoryRecord]:
    return [r for r in records if r.tenant_id == tenant_id]


def isolation_probe(records: Sequence[MemoryRecord], attacker_tenant: str) -> bool:
    leaks = [r for r in records if r.tenant_id != attacker_tenant]
    return len(leaks) == 0


# ---------------------------------------------------------------------------
# 10. Multi-Agent Topology & Consensus
# ---------------------------------------------------------------------------

def validate_topology(agents: Sequence[str], edges: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    agent_set = set(agents)
    for src, targets in edges.items():
        if src not in agent_set:
            return {"valid": False, "error": f"source {src} not in agents"}
        for tgt in targets:
            if tgt not in agent_set:
                return {"valid": False, "error": f"target {tgt} not in agents"}
    return {"valid": True}


def dependency_cycle(nodes: Sequence[str], edges: Mapping[str, Sequence[str]]) -> bool:
    indeg = {n: 0 for n in nodes}
    for src, targets in edges.items():
        for t in targets:
            indeg[t] = indeg.get(t, 0) + 1
    q = [n for n, d in indeg.items() if d == 0]
    visited = 0
    while q:
        curr = q.pop(0)
        visited += 1
        for tgt in edges.get(curr, []):
            indeg[tgt] -= 1
            if indeg[tgt] == 0:
                q.append(tgt)
    return visited != len(nodes)


# ---------------------------------------------------------------------------
# 11. Supply Chain, Incident, Compliance, Cache
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PackageTrustInput:
    package_name: str
    version: str
    provenance_signed: bool
    sbom_present: bool
    vulnerabilities: tuple[str, ...] = ()


def trust_decision(pkg: PackageTrustInput) -> str:
    if pkg.vulnerabilities:
        return "QUARANTINE"
    if not pkg.provenance_signed or not pkg.sbom_present:
        return "UNVERIFIED"
    return "TRUSTED"


class IncidentController:
    def __init__(self) -> None:
        self.kill_switch_engaged = False
        self.active_incidents: list[str] = []

    def trigger_kill_switch(self, incident_id: str) -> None:
        self.kill_switch_engaged = True
        self.active_incidents.append(incident_id)

    def can_execute(self) -> bool:
        return not self.kill_switch_engaged


@dataclass(frozen=True)
class Control:
    control_id: str
    satisfied: bool
    mandatory: bool = True


def profile_decision(controls: Sequence[Control]) -> str:
    for c in controls:
        if c.mandatory and not c.satisfied:
            return "NON_COMPLIANT"
    if all(c.satisfied for c in controls):
        return "COMPLIANT"
    return "CONDITIONALLY_COMPLIANT"


@dataclass(frozen=True)
class CacheContext:
    prompt_hash: str
    model_version: str
    tool_hash: str
    tenant_id: str


def semantic_key(ctx: CacheContext) -> str:
    raw = f"{ctx.tenant_id}:{ctx.model_version}:{ctx.prompt_hash}:{ctx.tool_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


def cache_reuse_decision(key1: str, key2: str) -> bool:
    return key1 == key2


@dataclass(frozen=True)
class ToolContract:
    name: str
    parameters_schema: Mapping[str, Any]
    output_schema: Mapping[str, Any]


def compare_tools(t1: ToolContract, t2: ToolContract) -> dict[str, Any]:
    if t1.name != t2.name:
        return {"compatible": False, "reason": "name mismatch"}
    bp = backward_compatibility(t1.parameters_schema, t2.parameters_schema)
    if not bp["compatible"]:
        return {"compatible": False, "reason": f"parameter schema incompatible: {bp['reason']}"}
    return {"compatible": True}


@dataclass(frozen=True)
class QualityResult:
    completeness: float
    validity: float
    anomaly_count: int


def quality_gate(res: QualityResult, min_comp: float = 0.95, max_anomalies: int = 0) -> bool:
    return res.completeness >= min_comp and res.anomaly_count <= max_anomalies


@dataclass(frozen=True)
class Usage:
    input_tokens: int
    output_tokens: int
    tool_calls: int


@dataclass(frozen=True)
class Rates:
    cost_per_1k_input: float = 0.0015
    cost_per_1k_output: float = 0.0020
    cost_per_tool_call: float = 0.0005


def calculate_cost(usage: Usage, rates: Rates) -> float:
    return (
        (usage.input_tokens / 1000.0) * rates.cost_per_1k_input
        + (usage.output_tokens / 1000.0) * rates.cost_per_1k_output
        + usage.tool_calls * rates.cost_per_tool_call
    )


def budget_decision(cost: float, max_budget: float) -> str:
    return "APPROVED" if cost <= max_budget else "BUDGET_EXCEEDED"


@dataclass(frozen=True)
class ProviderCandidate:
    provider: str
    latency_ms: float
    availability: float
    cost_per_token: float


def select_provider(candidates: Sequence[ProviderCandidate], max_latency: float = 1000.0, min_avail: float = 0.99) -> str:
    eligible = [c for c in candidates if c.latency_ms <= max_latency and c.availability >= min_avail]
    if not eligible:
        raise ValueError("no eligible providers meet SLA")
    best = min(eligible, key=lambda c: c.cost_per_token)
    return best.provider


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    effect: str  # ALLOW, DENY
    conditions: Mapping[str, Any]


def validate_rules(rules: Sequence[PolicyRule]) -> bool:
    return len(rules) > 0 and all(r.effect in ("ALLOW", "DENY") for r in rules)


def default_decision() -> str:
    return "DENY"


@dataclass(frozen=True)
class ActionPreview:
    action_type: str
    impact_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    reversible: bool


def ux_gate(preview: ActionPreview, user_confirmed: bool) -> bool:
    if preview.impact_level in ("HIGH", "CRITICAL") or not preview.reversible:
        return user_confirmed
    return True
