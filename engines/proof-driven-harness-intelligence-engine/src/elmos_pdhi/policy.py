"""K6 policy and semantic invariant engine.

Imported instruction files are inert data.  They are normalized into the
foundation :class:`RuleIR`, evaluated by an exact PDP, and enforced by a PEP
that fails closed for mutation.  Interrupt and repair operations are typed
``NOT_RUN`` effects; this module never executes repository-supplied commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Protocol, Sequence, cast

from .canonical import digest_object, require_sha256_digest
from .contracts import (
    AuthorityLevel,
    EvidenceRecord,
    EvidenceStatus,
    ExecutionContext,
    ResourceScope,
    RuleEnforcement,
    RuleIR,
)
from .errors import ConflictError, UnknownCapabilityError, ValidationError
from .registry import CAPABILITY_REGISTRY, OperationSpec


SUPPORTED_SOURCE_FAMILIES = frozenset(
    {
        "elmos",
        "agents",
        "cursor",
        "cline",
        "copilot",
        "github",
        "windsurf",
        "architecture-standard",
        "security-standard",
        "migration-constraint",
    }
)


AUTHORITY_PRECEDENCE: Mapping[AuthorityLevel, int] = MappingProxyType(
    {
        AuthorityLevel.FORMAL_PROOF: 80,
        AuthorityLevel.COMPILER: 70,
        AuthorityLevel.LSP: 60,
        AuthorityLevel.SEMANTIC_IR: 50,
        AuthorityLevel.AST: 40,
        AuthorityLevel.RUNTIME_EVIDENCE: 30,
        AuthorityLevel.TEXT_SEARCH: 20,
        AuthorityLevel.LLM_INFERENCE: 10,
    }
)


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} is required", code="INVALID_INPUT")
    return value


def _same_scope(left: ResourceScope, right: ResourceScope) -> bool:
    return (
        left.tenant_id,
        left.project_id,
        left.repository_id,
        left.input_revision,
    ) == (
        right.tenant_id,
        right.project_id,
        right.repository_id,
        right.input_revision,
    )


def _normalize_path(value: str) -> str:
    _required(value, "path")
    if "\\" in value:
        raise ValidationError("path must be POSIX", code="INVALID_POLICY_PATH")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError("policy path escapes repository", code="POLICY_SCOPE_ESCAPE")
    normalized = path.as_posix()
    if normalized != value.rstrip("/") and not (normalized == "." and value == "."):
        raise ValidationError("policy path is not normalized", code="INVALID_POLICY_PATH")
    return normalized


def _semver_key(value: str) -> tuple[int, int, int, int, str]:
    match = re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(.*)", value)
    if match is None:
        raise ValidationError("version must be semantic version", code="INVALID_VERSION")
    suffix = match.group(4)
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        1 if not suffix else 0,
        suffix,
    )


@dataclass(frozen=True, slots=True)
class RuleSource:
    source_family: str
    source_path: str
    source_digest: str
    assigned_namespace: str
    assigned_authority: AuthorityLevel
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.source_family not in SUPPORTED_SOURCE_FAMILIES:
            raise ValidationError("unsupported rule source family", code="UNSUPPORTED_RULE_SOURCE")
        _normalize_path(self.source_path)
        require_sha256_digest(self.source_digest, field="source_digest")
        _required(self.assigned_namespace, "assigned_namespace")
        if not isinstance(self.payload, Mapping):
            raise ValidationError("rule source payload must be an object", code="INVALID_RULE_SOURCE")


@dataclass(frozen=True, slots=True)
class NormalizedRule:
    rule: RuleIR
    source_family: str
    source_path: str
    source_digest: str
    normalized_digest: str
    unsupported_fields: tuple[str, ...]
    authority_claim_ignored: bool


class RuleNormalizer:
    """Allowlisted normalization; source authority claims never grant authority."""

    _ALLOWED_FIELDS = frozenset(
        {
            "rule_id",
            "name",
            "version",
            "scope",
            "enforcement",
            "trigger",
            "invariant",
            "evidence_requirement",
            "remediation",
            "compatibility",
            "namespace",
            "authority",
        }
    )

    @staticmethod
    def _tuple(value: object, field_name: str, *, required: bool = False) -> tuple[str, ...]:
        if value is None:
            if required:
                raise ValidationError(f"{field_name} is required", code="INVALID_RULE_SOURCE")
            return ()
        if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
            raise ValidationError(f"{field_name} must be a string list", code="INVALID_RULE_SOURCE")
        return tuple(value)

    def normalize(self, source: RuleSource) -> NormalizedRule:
        data = source.payload
        unsupported = tuple(sorted(set(data).difference(self._ALLOWED_FIELDS)))
        try:
            enforcement = RuleEnforcement(str(data["enforcement"]).upper())
        except (KeyError, ValueError) as exc:
            raise ValidationError("invalid rule enforcement", code="INVALID_RULE_SOURCE") from exc
        trigger = data.get("trigger")
        if trigger is not None and not isinstance(trigger, Mapping):
            raise ValidationError("trigger must be an object", code="INVALID_RULE_SOURCE")
        compatibility = data.get("compatibility")
        if compatibility is not None and not isinstance(compatibility, Mapping):
            raise ValidationError("compatibility must be an object", code="INVALID_RULE_SOURCE")
        authority_claim_ignored = "authority" in data and str(data["authority"]) != source.assigned_authority.value
        rule = RuleIR(
            rule_id=str(data.get("rule_id", "")),
            namespace=source.assigned_namespace,
            name=str(data.get("name", "")),
            version=str(data.get("version", "")),
            authority=source.assigned_authority,
            scope=self._tuple(data.get("scope"), "scope", required=True),
            enforcement=enforcement,
            trigger=dict(trigger) if trigger is not None else None,
            invariant=str(data["invariant"]) if data.get("invariant") is not None else None,
            evidence_requirement=self._tuple(data.get("evidence_requirement"), "evidence_requirement"),
            remediation=str(data["remediation"]) if data.get("remediation") is not None else None,
            compatibility=dict(compatibility) if compatibility is not None else None,
        )
        normalized_digest = digest_object(
            {
                "rule": rule,
                "source_family": source.source_family,
                "source_path": source.source_path,
                "source_digest": source.source_digest,
                "unsupported_fields": unsupported,
            },
            domain="normalized-rule",
        )
        return NormalizedRule(
            rule,
            source.source_family,
            source.source_path,
            source.source_digest,
            normalized_digest,
            unsupported,
            authority_claim_ignored,
        )


class TriggerKind(StrEnum):
    ALWAYS = "always"
    REGEX = "regex"
    AST = "ast"
    SEMANTIC = "semantic"
    RUNTIME = "runtime"
    TOOL = "tool"
    PATH = "path"
    SYMBOL = "symbol"


@dataclass(frozen=True, slots=True)
class PolicyEvaluationContext:
    execution: ExecutionContext
    path: str | None = None
    symbol: str | None = None
    tool: str | None = None
    text: str | None = None
    ast_facts: Mapping[str, str] = field(default_factory=dict)
    semantic_facts: Mapping[str, str] = field(default_factory=dict)
    runtime_facts: Mapping[str, str] = field(default_factory=dict)
    evidence_records: Mapping[str, EvidenceRecord] = field(default_factory=dict)
    mutation: bool = False


class TriggerMatcher:
    MAX_PATTERN = 2_048
    MAX_TEXT = 1_000_000

    @staticmethod
    def _structured_match(trigger: Mapping[str, Any], facts: Mapping[str, str]) -> bool:
        fact = trigger.get("fact")
        expected = trigger.get("equals")
        if not isinstance(fact, str) or not isinstance(expected, str):
            raise ValidationError("structured trigger needs fact/equals", code="INVALID_POLICY_TRIGGER")
        return facts.get(fact) == expected

    def matches(self, rule: RuleIR, context: PolicyEvaluationContext) -> bool:
        if context.path is not None:
            path = _normalize_path(context.path)
            if not any(
                scope == "." or path == scope or path.startswith(scope + "/")
                for scope in rule.scope
            ):
                return False
        trigger = rule.trigger
        if trigger is None:
            return True
        try:
            kind = TriggerKind(str(trigger.get("kind", "")))
        except ValueError as exc:
            raise ValidationError("unknown trigger kind", code="UNKNOWN_POLICY_TRIGGER") from exc
        if kind is TriggerKind.ALWAYS:
            return True
        if kind is TriggerKind.REGEX:
            pattern = trigger.get("pattern")
            if (
                not isinstance(pattern, str)
                or len(pattern) > self.MAX_PATTERN
                or "(" in pattern
                or ")" in pattern
                or re.search(r"\\[1-9]", pattern) is not None
            ):
                raise ValidationError("regex trigger is invalid", code="INVALID_POLICY_TRIGGER")
            if context.text is None or len(context.text) > self.MAX_TEXT:
                return False
            try:
                return re.search(pattern, context.text) is not None
            except re.error as exc:
                raise ValidationError("regex trigger cannot compile", code="INVALID_POLICY_TRIGGER") from exc
        if kind is TriggerKind.AST:
            return self._structured_match(trigger, context.ast_facts)
        if kind is TriggerKind.SEMANTIC:
            return self._structured_match(trigger, context.semantic_facts)
        if kind is TriggerKind.RUNTIME:
            return self._structured_match(trigger, context.runtime_facts)
        if kind is TriggerKind.TOOL:
            expected = trigger.get("tool")
            if not isinstance(expected, str):
                raise ValidationError("tool trigger is invalid", code="INVALID_POLICY_TRIGGER")
            return context.tool == expected
        if kind is TriggerKind.PATH:
            pattern = trigger.get("pattern")
            if not isinstance(pattern, str) or ".." in PurePosixPath(pattern).parts or pattern.startswith("/"):
                raise ValidationError("path trigger is invalid", code="INVALID_POLICY_TRIGGER")
            return context.path is not None and fnmatchcase(_normalize_path(context.path), pattern)
        if kind is TriggerKind.SYMBOL:
            pattern = trigger.get("pattern")
            if not isinstance(pattern, str):
                raise ValidationError("symbol trigger is invalid", code="INVALID_POLICY_TRIGGER")
            return context.symbol is not None and fnmatchcase(context.symbol, pattern)
        raise AssertionError("unreachable trigger kind")


@dataclass(frozen=True, slots=True)
class PolicyConflict:
    conflict_id: str
    conflict_key: str
    rule_ids: tuple[str, ...]
    selected_rule_id: str | None
    resolved: bool
    explanation: str


class PolicyPrecedence:
    @staticmethod
    def _specificity(rule: RuleIR) -> int:
        return max((len(PurePosixPath(item).parts) for item in rule.scope), default=0)

    @staticmethod
    def _override_ids(rule: RuleIR) -> frozenset[str]:
        if rule.compatibility is None:
            return frozenset()
        raw = rule.compatibility.get("overrides", ())
        if not isinstance(raw, (tuple, list)) or any(not isinstance(item, str) for item in raw):
            raise ValidationError("compatibility.overrides must be a string list", code="INVALID_OVERRIDE")
        return frozenset(raw)

    def resolve(self, rules: Sequence[RuleIR]) -> tuple[tuple[RuleIR, ...], tuple[PolicyConflict, ...]]:
        groups: dict[str, list[RuleIR]] = {}
        for rule in rules:
            raw_key = rule.compatibility.get("conflict_key") if rule.compatibility is not None else None
            key = raw_key if isinstance(raw_key, str) and raw_key else f"{rule.namespace}:{rule.name}"
            groups.setdefault(key, []).append(rule)
        selected: list[RuleIR] = []
        conflicts: list[PolicyConflict] = []
        for key, candidates in groups.items():
            if len(candidates) == 1:
                selected.append(candidates[0])
                continue
            overrides = [
                candidate
                for candidate in candidates
                if set(item.rule_id for item in candidates if item is not candidate).issubset(
                    self._override_ids(candidate)
                )
                and all(
                    AUTHORITY_PRECEDENCE[candidate.authority]
                    >= AUTHORITY_PRECEDENCE[item.authority]
                    and self._specificity(candidate) >= self._specificity(item)
                    for item in candidates
                    if item is not candidate
                )
            ]
            if len(overrides) == 1:
                winner = overrides[0]
                resolved = True
                explanation = "explicit override selected the rule"
            else:
                ranked = sorted(
                    candidates,
                    key=lambda item: (
                        AUTHORITY_PRECEDENCE[item.authority],
                        self._specificity(item),
                        _semver_key(item.version),
                        item.namespace,
                    ),
                    reverse=True,
                )
                best = (
                    AUTHORITY_PRECEDENCE[ranked[0].authority],
                    self._specificity(ranked[0]),
                    _semver_key(ranked[0].version),
                )
                peers = [
                    item
                    for item in ranked
                    if (
                        AUTHORITY_PRECEDENCE[item.authority],
                        self._specificity(item),
                        _semver_key(item.version),
                    )
                    == best
                ]
                incompatible = len({item.enforcement for item in peers}) > 1
                winner = ranked[0]
                resolved = not incompatible and len(peers) == 1
                explanation = (
                    "authority, scope specificity and version selected the rule"
                    if resolved
                    else "equal-precedence rules conflict and require an explicit override"
                )
            conflict = PolicyConflict(
                conflict_id=digest_object(
                    {"key": key, "rules": tuple(sorted(item.rule_id for item in candidates))},
                    domain="policy-conflict",
                ),
                conflict_key=key,
                rule_ids=tuple(sorted(item.rule_id for item in candidates)),
                selected_rule_id=winner.rule_id if resolved else None,
                resolved=resolved,
                explanation=explanation,
            )
            conflicts.append(conflict)
            if resolved:
                selected.append(winner)
        return tuple(selected), tuple(conflicts)


class PDPDecision(StrEnum):
    PERMIT = "PERMIT"
    DENY = "DENY"
    INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ObligationType(StrEnum):
    CONTEXT = "CONTEXT"
    INJECT = "INJECT"
    INTERRUPT = "INTERRUPT"
    BLOCK = "BLOCK"
    REPAIR = "REPAIR"
    AUDIT = "AUDIT"


@dataclass(frozen=True, slots=True)
class PolicyObligation:
    obligation_id: str
    rule_id: str
    kind: ObligationType
    required_evidence: tuple[str, ...]
    remediation: str | None


@dataclass(frozen=True, slots=True)
class PolicyDecisionRecord:
    decision_id: str
    scope: ResourceScope
    execution_digest: str
    decision: PDPDecision
    matched_rule_ids: tuple[str, ...]
    conflicts: tuple[PolicyConflict, ...]
    obligations: tuple[PolicyObligation, ...]
    reason: str


class PolicyDecisionPoint:
    def __init__(
        self,
        scope: ResourceScope,
        rules: Iterable[RuleIR],
        *,
        matcher: TriggerMatcher | None = None,
        precedence: PolicyPrecedence | None = None,
    ) -> None:
        self._scope = scope
        self._rules = tuple(rules)
        ids = [rule.rule_id for rule in self._rules]
        if len(ids) != len(set(ids)):
            raise ConflictError("policy rule ids must be unique", code="DUPLICATE_RULE_ID")
        self._matcher = matcher or TriggerMatcher()
        self._precedence = precedence or PolicyPrecedence()

    @staticmethod
    def _obligation(rule: RuleIR) -> PolicyObligation:
        kinds = {
            RuleEnforcement.CONTEXT: ObligationType.CONTEXT,
            RuleEnforcement.JIT_GUARD: ObligationType.INJECT,
            RuleEnforcement.INTERRUPT: ObligationType.INTERRUPT,
            RuleEnforcement.BLOCK: ObligationType.BLOCK,
            RuleEnforcement.AUTO_REPAIR: ObligationType.REPAIR,
            RuleEnforcement.AUDIT: ObligationType.AUDIT,
        }
        return PolicyObligation(
            digest_object(
                {"rule_id": rule.rule_id, "kind": kinds[rule.enforcement]},
                domain="policy-obligation",
            ),
            rule.rule_id,
            kinds[rule.enforcement],
            rule.evidence_requirement,
            rule.remediation,
        )

    def evaluate(self, context: PolicyEvaluationContext) -> PolicyDecisionRecord:
        execution_digest = context.execution.content_digest()
        if not _same_scope(context.execution.scope, self._scope):
            return PolicyDecisionRecord(
                digest_object(
                    {"execution": execution_digest, "error": "POLICY_SCOPE_MISMATCH"},
                    domain="policy-decision",
                ),
                context.execution.scope,
                execution_digest,
                PDPDecision.INDETERMINATE,
                (),
                (),
                (),
                "policy bundle scope mismatch",
            )
        try:
            matched = tuple(rule for rule in self._rules if self._matcher.matches(rule, context))
            selected, conflicts = self._precedence.resolve(matched)
        except Exception as exc:
            return PolicyDecisionRecord(
                digest_object(
                    {"task": context.execution.task_id, "error": type(exc).__name__},
                    domain="policy-decision",
                ),
                context.execution.scope,
                execution_digest,
                PDPDecision.INDETERMINATE,
                (),
                (),
                (),
                f"policy evaluation failed: {type(exc).__name__}",
            )
        unresolved = tuple(conflict for conflict in conflicts if not conflict.resolved)
        if unresolved:
            decision = PDPDecision.INDETERMINATE
            reason = "unresolved policy conflict"
            obligations = tuple(
                PolicyObligation(
                    digest_object({"conflict": item.conflict_id}, domain="policy-obligation"),
                    item.rule_ids[0],
                    ObligationType.BLOCK,
                    (),
                    "resolve policy conflict explicitly",
                )
                for item in unresolved
            )
        elif not selected:
            decision = PDPDecision.NOT_APPLICABLE
            reason = "no policy matched"
            obligations = ()
        else:
            obligations = tuple(self._obligation(rule) for rule in selected)
            missing_or_unknown = tuple(
                requirement
                for rule in selected
                for requirement in rule.evidence_requirement
                if (
                    context.evidence_records.get(requirement) is None
                    or context.evidence_records[requirement].status is not EvidenceStatus.VALID
                    or context.evidence_records[requirement].scope is None
                    or not _same_scope(
                        cast(ResourceScope, context.evidence_records[requirement].scope),
                        context.execution.scope,
                    )
                )
            )
            if missing_or_unknown:
                decision = PDPDecision.INDETERMINATE
                reason = "required policy evidence is unknown or non-valid"
                obligations = (
                    *obligations,
                    PolicyObligation(
                        digest_object(
                            {"requirements": tuple(sorted(set(missing_or_unknown)))},
                            domain="policy-obligation",
                        ),
                        selected[0].rule_id,
                        ObligationType.BLOCK,
                        tuple(sorted(set(missing_or_unknown))),
                        "produce independently verifiable invariant evidence",
                    ),
                )
            elif any(
                item.enforcement
                in {RuleEnforcement.INTERRUPT, RuleEnforcement.BLOCK, RuleEnforcement.AUTO_REPAIR}
                for item in selected
            ):
                decision = PDPDecision.DENY
                reason = "matched policy requires interruption, block or governed repair"
            else:
                decision = PDPDecision.PERMIT
                reason = "matched policies permit with obligations"
        decision_id = digest_object(
            {
                "scope": context.execution.scope,
                "execution": execution_digest,
                "matched": tuple(rule.rule_id for rule in selected),
                "conflicts": tuple(item.conflict_id for item in conflicts),
                "decision": decision,
            },
            domain="policy-decision",
        )
        return PolicyDecisionRecord(
            decision_id,
            context.execution.scope,
            execution_digest,
            decision,
            tuple(rule.rule_id for rule in selected),
            conflicts,
            obligations,
            reason,
        )


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    violation_id: str
    rule_id: str
    scope: ResourceScope
    obligation: ObligationType
    required_evidence: tuple[str, ...]
    remediation: str
    decision_id: str


@dataclass(frozen=True, slots=True)
class PolicyRepairPlan:
    plan_id: str
    rule_id: str
    scope: ResourceScope
    remediation: str
    requires_approval: bool = True
    requires_reverification: bool = True


class PolicyEffectStatus(StrEnum):
    NOT_RUN = "NOT_RUN"


@dataclass(frozen=True, slots=True)
class PolicyEffectRequest:
    request_id: str
    context: ExecutionContext
    obligation_id: str
    kind: ObligationType
    repair_plan: PolicyRepairPlan | None
    status: PolicyEffectStatus = PolicyEffectStatus.NOT_RUN
    external_evidence_status: PolicyEffectStatus = PolicyEffectStatus.NOT_RUN

    def __post_init__(self) -> None:
        if self.kind not in {ObligationType.INTERRUPT, ObligationType.REPAIR}:
            raise ValidationError("only interrupt/repair are external policy effects", code="INVALID_POLICY_EFFECT")
        if self.status is not PolicyEffectStatus.NOT_RUN or self.external_evidence_status is not PolicyEffectStatus.NOT_RUN:
            raise ValidationError("external policy effects must originate NOT_RUN", code="FABRICATED_POLICY_EFFECT")


@dataclass(frozen=True, slots=True)
class PolicyEnforcementResult:
    allowed: bool
    decision: PolicyDecisionRecord
    violations: tuple[PolicyViolation, ...]
    effect_requests: tuple[PolicyEffectRequest, ...]


@dataclass(frozen=True, slots=True)
class PolicyAuditRecord:
    audit_id: str
    scope: ResourceScope
    actor_id: str
    task_id: str
    decision_id: str
    decision: PDPDecision
    rule_ids: tuple[str, ...]
    violation_ids: tuple[str, ...]
    effect_request_ids: tuple[str, ...]
    occurred_at: datetime


class PolicyAuditStore(Protocol):
    durable: bool

    def append(self, record: PolicyAuditRecord) -> None: ...

    def list_for_scope(self, scope: ResourceScope) -> tuple[PolicyAuditRecord, ...]: ...


class InMemoryPolicyAuditStore:
    durable = False

    def __init__(self) -> None:
        self._records: list[PolicyAuditRecord] = []

    def append(self, record: PolicyAuditRecord) -> None:
        if any(existing.audit_id == record.audit_id for existing in self._records):
            return
        self._records.append(record)

    def list_for_scope(self, scope: ResourceScope) -> tuple[PolicyAuditRecord, ...]:
        return tuple(record for record in self._records if _same_scope(record.scope, scope))


class PolicyEnforcementPoint:
    def __init__(self, audit_store: PolicyAuditStore) -> None:
        self._audit_store = audit_store

    def enforce(
        self,
        context: ExecutionContext,
        decision: PolicyDecisionRecord,
        *,
        mutation: bool,
        now: datetime,
    ) -> PolicyEnforcementResult:
        if not _same_scope(context.scope, decision.scope):
            raise ValidationError("PDP decision scope mismatch", code="POLICY_SCOPE_MISMATCH")
        if context.content_digest() != decision.execution_digest:
            raise ValidationError(
                "PDP decision execution binding mismatch", code="POLICY_EXECUTION_MISMATCH"
            )
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValidationError("policy enforcement time must be aware", code="INVALID_TIME")
        allowed = decision.decision is PDPDecision.PERMIT or (
            decision.decision is PDPDecision.NOT_APPLICABLE and not mutation
        )
        violations: list[PolicyViolation] = []
        effects: list[PolicyEffectRequest] = []
        for obligation in decision.obligations:
            if obligation.kind in {ObligationType.BLOCK, ObligationType.INTERRUPT, ObligationType.REPAIR}:
                violation = PolicyViolation(
                    digest_object(
                        {"decision": decision.decision_id, "obligation": obligation.obligation_id},
                        domain="policy-violation",
                    ),
                    obligation.rule_id,
                    context.scope,
                    obligation.kind,
                    obligation.required_evidence,
                    obligation.remediation or "manual policy resolution required",
                    decision.decision_id,
                )
                violations.append(violation)
                if obligation.kind in {ObligationType.INTERRUPT, ObligationType.REPAIR}:
                    repair = None
                    if obligation.kind is ObligationType.REPAIR:
                        repair = PolicyRepairPlan(
                            digest_object(
                                {"violation": violation.violation_id}, domain="policy-repair-plan"
                            ),
                            obligation.rule_id,
                            context.scope,
                            violation.remediation,
                        )
                    effects.append(
                        PolicyEffectRequest(
                            digest_object(
                                {
                                    "idempotency_key": context.idempotency_key,
                                    "context": context,
                                    "obligation": obligation.obligation_id,
                                },
                                domain="policy-effect",
                            ),
                            context,
                            obligation.obligation_id,
                            obligation.kind,
                            repair,
                        )
                    )
        if decision.decision in {PDPDecision.DENY, PDPDecision.INDETERMINATE} or (
            mutation and decision.decision is PDPDecision.NOT_APPLICABLE
        ):
            allowed = False
        if not allowed and not violations:
            violations.append(
                PolicyViolation(
                    digest_object(
                        {"decision": decision.decision_id, "default_deny": True},
                        domain="policy-violation",
                    ),
                    decision.matched_rule_ids[0]
                    if decision.matched_rule_ids
                    else "pdhi.default-deny",
                    context.scope,
                    ObligationType.BLOCK,
                    (),
                    "define an explicit applicable permit or resolve the policy decision",
                    decision.decision_id,
                )
            )
        audit = PolicyAuditRecord(
            digest_object(
                {
                    "decision": decision.decision_id,
                    "actor": context.actor_id,
                    "task": context.task_id,
                    "at": now,
                },
                domain="policy-audit",
            ),
            context.scope,
            context.actor_id,
            context.task_id,
            decision.decision_id,
            decision.decision,
            decision.matched_rule_ids,
            tuple(item.violation_id for item in violations),
            tuple(item.request_id for item in effects),
            now,
        )
        self._audit_store.append(audit)
        return PolicyEnforcementResult(allowed, decision, tuple(violations), tuple(effects))


class StreamSemanticGuard:
    """Evaluate ordered contexts and stop at the first fail-closed decision."""

    def __init__(self, pdp: PolicyDecisionPoint, pep: PolicyEnforcementPoint) -> None:
        self._pdp = pdp
        self._pep = pep

    def evaluate(
        self, contexts: Iterable[PolicyEvaluationContext], *, now: datetime
    ) -> tuple[PolicyEnforcementResult, ...]:
        results: list[PolicyEnforcementResult] = []
        for item in contexts:
            decision = self._pdp.evaluate(item)
            result = self._pep.enforce(
                item.execution, decision, mutation=item.mutation, now=now
            )
            results.append(result)
            if not result.allowed:
                break
        return tuple(results)


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    capability: str
    source_owner: str
    canonical_owner: str
    handler: str
    input_contract: str
    output_contract: str
    external_effect: bool = False


_K6_BINDING_ROWS = (
    ("rule-source-discovery", "K6", "K6", "SUPPORTED_SOURCE_FAMILIES", "repository inventory", "RuleSource[]", False),
    ("rule-normalizer", "K6", "K6", "RuleNormalizer.normalize", "RuleSource", "NormalizedRule", False),
    ("cross-harness-rule-import", "K6", "K6", "RuleNormalizer.normalize", "external inert rule", "NormalizedRule", False),
    ("policy-namespace", "K6", "K6", "RuleSource.assigned_namespace", "trusted namespace", "RuleIR.namespace", False),
    ("policy-versioning", "K6", "K6", "RuleIR.version", "semantic version", "precedence input", False),
    ("policy-authority", "K6", "K6", "AUTHORITY_PRECEDENCE", "AuthorityLevel", "authority rank", False),
    ("policy-precedence", "K6", "K6", "PolicyPrecedence.resolve", "RuleIR[]", "selected rules", False),
    ("policy-conflict-explainer", "K6", "K6", "PolicyPrecedence.resolve", "conflicting RuleIR[]", "PolicyConflict[]", False),
    ("always-apply-policy", "K6", "K6", "TriggerMatcher.matches[always]", "RuleIR", "bool", False),
    ("lazy-rulebook", "K6", "K6", "PolicyDecisionPoint", "scoped RuleIR[]", "PDP", False),
    ("regex-trigger", "K6", "K6", "TriggerMatcher.matches[regex]", "text+pattern", "bool", False),
    ("ast-trigger", "K6", "K6", "TriggerMatcher.matches[ast]", "AST facts", "bool", False),
    ("semantic-trigger", "K6", "K6", "TriggerMatcher.matches[semantic]", "semantic facts", "bool", False),
    ("runtime-trigger", "K6", "K6", "TriggerMatcher.matches[runtime]", "runtime facts", "bool", False),
    ("tool-scope-trigger", "K6", "K6", "TriggerMatcher.matches[tool]", "tool", "bool", False),
    ("path-scope-trigger", "K6", "K6", "TriggerMatcher.matches[path]", "path", "bool", False),
    ("symbol-scope-trigger", "K6", "K6", "TriggerMatcher.matches[symbol]", "symbol", "bool", False),
    ("jit-rule-injection", "K6", "K6", "PolicyDecisionPoint.evaluate", "PolicyEvaluationContext", "INJECT obligation", False),
    ("stream-semantic-guard", "K6", "K6", "StreamSemanticGuard.evaluate", "context stream", "PolicyEnforcementResult[]", False),
    ("policy-interrupt", "K6", "K6", "PolicyEnforcementPoint.enforce", "INTERRUPT obligation", "PolicyEffectRequest", True),
    ("policy-block", "K6", "K6", "PolicyEnforcementPoint.enforce", "BLOCK obligation", "PolicyViolation", False),
    ("policy-auto-repair", "K6", "K6", "PolicyEnforcementPoint.enforce", "REPAIR obligation", "PolicyRepairPlan+PolicyEffectRequest", True),
    ("invariant-evidence", "K6", "K6", "PolicyDecisionPoint.evaluate", "evidence statuses", "PDP decision", False),
    ("policy-audit", "K6", "K6", "PolicyAuditStore.append", "PolicyAuditRecord", "durable audit", False),
)

K6_CAPABILITIES = tuple(row[0] for row in _K6_BINDING_ROWS)
K6_OPERATION_BINDINGS: Mapping[str, CapabilityBinding] = MappingProxyType(
    {row[0]: CapabilityBinding(*row) for row in _K6_BINDING_ROWS}
)
K6_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {name: CAPABILITY_REGISTRY[name] for name in K6_CAPABILITIES}
)


def resolve_k6_binding(capability: str) -> CapabilityBinding:
    try:
        return K6_OPERATION_BINDINGS[capability]
    except KeyError as exc:
        raise UnknownCapabilityError(
            "unknown K6 capability; generic fallback is forbidden",
            code="UNKNOWN_K6_CAPABILITY",
            details={"capability": capability},
        ) from exc


if len(K6_CAPABILITIES) != 24 or len(set(K6_CAPABILITIES)) != len(K6_CAPABILITIES):
    raise RuntimeError("K6 capability bindings must contain exactly 24 unique operations")
