"""Tiered security assurance: monotonic controls, derived tiers, visible gaps.

Four assurance tiers, T0 through T3, each one a strict superset of the tier
below.  The monotonicity is structural rather than aspirational: a tier's
control set is *built* by extending the tier beneath it, and the module refuses
to import if that ever stops being true.  A table of independently-edited sets
drifts within a release or two, and the drift is invisible until the day a
higher tier turns out to require fewer checks than a lower one.

The tier is derived from the change set, not requested by the caller.  Touching
authentication, cryptography, payments, infrastructure-as-code or CI, adding an
external dependency, or changing a public API each force a minimum tier, and the
classifier reports which pattern fired so the escalation is arguable rather than
mysterious.  A caller may ask for more assurance than the change set requires;
asking for less silently escalates and says so.

Two rules exist because their opposites are how security gates get bypassed in
practice.  A required control with no report is ``MISSING`` — never inferred to
have passed, and never satisfied by an LLM review standing in for a scanner,
because a model's opinion about a diff is not a static analysis run.  And a
finding whose severity nobody has established is treated as the *highest*
severity until it is triaged, not the lowest: "we don't know how bad this is"
must cost someone an investigation, not nothing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from fnmatch import fnmatchcase
from typing import Any

from .contracts import (
    digest,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_bool,
    require_identifier,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .ports import EventStore
from .registry import register

__all__ = [
    "AssuranceResult",
    "ChangeSet",
    "Control",
    "ControlMethod",
    "ControlReport",
    "ControlStatus",
    "Finding",
    "FindingKind",
    "FindingStatus",
    "PathCategory",
    "PathRule",
    "Reason",
    "ReasonCode",
    "SecurityDecision",
    "SecurityPolicy",
    "Severity",
    "Tier",
    "Trigger",
    "TriggerKind",
    "Waiver",
    "PATH_RULES",
    "assess",
    "classify_path",
    "controls_for",
    "derive_tier",
    "handle",
    "record_assessment",
]

register_codes(
    Category.RELEASE,
    "SECURITY_GATE_FAILED",
    "WAIVER_INVALID",
    "WAIVER_EXPIRED",
)
register_codes(
    Category.POLICY,
    "PROMPT_INJECTION_DETECTED",
    "TENANT_BOUNDARY_BROKEN",
)
register_codes(
    Category.SANDBOX,
    "SECRET_EXPOSURE",
)
register_codes(
    Category.VERIFICATION,
    "CONTROL_MISSING",
    "SEVERITY_UNTRIAGED",
)
register_codes(
    Category.SEMANTIC,
    "TIER_MONOTONICITY_VIOLATED",
    "ASSURANCE_TIER_UNKNOWN",
)


class Tier(StrEnum):
    """Assurance tiers, cheapest first."""

    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"

    @property
    def rank(self) -> int:
        return _TIER_ORDER.index(self)


_TIER_ORDER: tuple[Tier, ...] = (Tier.T0, Tier.T1, Tier.T2, Tier.T3)


class Control(StrEnum):
    """The seven controls this kernel knows how to require."""

    SECRET_SCAN = "secret-scan"  # noqa: S105 - a control/verdict name, not a credential
    DEPENDENCY_ADVISORY = "dependency-advisory"
    STATIC_ANALYSIS = "static-analysis"
    LICENSE_CHECK = "license-check"
    SENSITIVE_PATH_REVIEW = "sensitive-path-review"
    SECOND_REVIEW = "second-review"
    PROVENANCE_ATTESTATION = "provenance-attestation"


#: What each tier *adds* to the tier beneath it.  Nothing is ever removed, and
#: :func:`controls_for` composes rather than looks up, so a higher tier cannot
#: require fewer controls even if someone edits this table carelessly.
_TIER_ADDITIONS: Mapping[Tier, tuple[Control, ...]] = {
    Tier.T0: (Control.SECRET_SCAN,),
    Tier.T1: (Control.DEPENDENCY_ADVISORY, Control.STATIC_ANALYSIS),
    Tier.T2: (Control.LICENSE_CHECK, Control.SENSITIVE_PATH_REVIEW),
    Tier.T3: (Control.SECOND_REVIEW, Control.PROVENANCE_ATTESTATION),
}


def controls_for(tier: Tier) -> tuple[Control, ...]:
    """Every control required at ``tier``, in declaration order.

    Built by extension: the result for ``T2`` literally contains the result for
    ``T1``.  Callers can therefore compare tiers by set inclusion and be right.
    """

    if not isinstance(tier, Tier):
        raise KernelError(
            code="ASSURANCE_TIER_UNKNOWN",
            message=f"unknown assurance tier {tier!r}",
            recommended_action=f"use one of {[item.value for item in _TIER_ORDER]}",
        )
    collected: list[Control] = []
    for level in _TIER_ORDER:
        collected.extend(_TIER_ADDITIONS[level])
        if level is tier:
            break
    return tuple(collected)


def _check_monotonic() -> None:
    """Fail at import if the control ladder ever stops being monotonic."""

    previous: frozenset[Control] = frozenset()
    for level in _TIER_ORDER:
        current = frozenset(controls_for(level))
        if not current.issuperset(previous):
            raise KernelError(
                code="TIER_MONOTONICITY_VIOLATED",
                message=(
                    f"tier {level} requires {sorted(str(item) for item in previous - current)} "
                    "fewer controls than the tier below it"
                ),
                recommended_action="tiers may only add controls, never remove them",
            )
        previous = current


_check_monotonic()


# --- change-set classification -----------------------------------------------


class PathCategory(StrEnum):
    """Why a path is sensitive."""

    AUTH = "auth"
    CRYPTO = "crypto"
    PAYMENT = "payment"
    IAC = "iac"
    CI = "ci"


class TriggerKind(StrEnum):
    """What forced a minimum tier."""

    SENSITIVE_PATH = "SENSITIVE_PATH"
    NEW_EXTERNAL_DEPENDENCY = "NEW_EXTERNAL_DEPENDENCY"
    PUBLIC_API_CHANGE = "PUBLIC_API_CHANGE"
    BASELINE = "BASELINE"
    CALLER_REQUEST = "CALLER_REQUEST"


@dataclass(frozen=True, slots=True)
class PathRule:
    """One explicit pattern that raises the floor.

    The patterns use ``fnmatch`` semantics where ``*`` crosses directory
    separators.  That over-matches rather than under-matches, which is the
    correct direction for a rule whose failure mode is "we did not notice this
    was the auth code".
    """

    rule_id: str
    pattern: str
    category: PathCategory
    minimum_tier: Tier
    rationale: str

    def matches(self, path: str) -> bool:
        return fnmatchcase(path, self.pattern)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "pattern": self.pattern,
            "category": str(self.category),
            "minimumTier": str(self.minimum_tier),
            "rationale": self.rationale,
        }


#: Ordered, explicit and auditable.  The first rule that matches a path is the
#: one reported, so the ordering is part of the contract: the most severe
#: categories come first.
PATH_RULES: tuple[PathRule, ...] = (
    PathRule("auth-dir", "*/auth/*", PathCategory.AUTH, Tier.T3,
             "authentication and authorisation logic"),
    PathRule("auth-name", "*auth[nz]*", PathCategory.AUTH, Tier.T3,
             "authn/authz module by name"),
    PathRule("auth-session", "*session*", PathCategory.AUTH, Tier.T3,
             "session handling"),
    PathRule("auth-login", "*login*", PathCategory.AUTH, Tier.T3, "login flow"),
    PathRule("crypto-dir", "*/crypto/*", PathCategory.CRYPTO, Tier.T3,
             "cryptographic primitives"),
    PathRule("crypto-key", "*key*", PathCategory.CRYPTO, Tier.T3, "key material handling"),
    PathRule("crypto-secret", "*secret*", PathCategory.CRYPTO, Tier.T3, "secret handling"),
    PathRule("crypto-token", "*token*", PathCategory.CRYPTO, Tier.T3, "token issuance"),
    PathRule("payment-dir", "*/payment*/*", PathCategory.PAYMENT, Tier.T3, "payment flow"),
    PathRule("payment-billing", "*/billing/*", PathCategory.PAYMENT, Tier.T3, "billing flow"),
    PathRule("payment-checkout", "*checkout*", PathCategory.PAYMENT, Tier.T3, "checkout flow"),
    PathRule("ci-github", ".github/workflows/*", PathCategory.CI, Tier.T3,
             "CI definition; a change here can exfiltrate every secret in the org"),
    PathRule("ci-gitlab", "*.gitlab-ci.yml", PathCategory.CI, Tier.T3, "CI definition"),
    PathRule("ci-jenkins", "*Jenkinsfile*", PathCategory.CI, Tier.T3, "CI definition"),
    PathRule("iac-terraform", "*.tf", PathCategory.IAC, Tier.T2, "infrastructure as code"),
    PathRule("iac-terraform-dir", "*/terraform/*", PathCategory.IAC, Tier.T2,
             "infrastructure as code"),
    PathRule("iac-k8s", "*/k8s/*", PathCategory.IAC, Tier.T2, "cluster manifests"),
    PathRule("iac-helm", "*/helm/*", PathCategory.IAC, Tier.T2, "cluster manifests"),
    PathRule("iac-docker", "*Dockerfile*", PathCategory.IAC, Tier.T2, "image definition"),
)


@dataclass(frozen=True, slots=True)
class Trigger:
    """One reason the minimum tier is what it is."""

    kind: TriggerKind
    subject: str
    tier: Tier
    rule_id: str = ""
    pattern: str = ""
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "subject": self.subject,
            "tier": str(self.tier),
            "ruleId": self.rule_id,
            "pattern": self.pattern,
            "detail": self.detail,
        }


def classify_path(path: str) -> Trigger | None:
    """Return the first matching rule as a trigger, or ``None``.

    Reporting the rule and the pattern — not just "sensitive" — is what makes a
    disputed escalation resolvable without reading this file.
    """

    text = require_str(path, "path", max_length=1024)
    for rule in PATH_RULES:
        if rule.matches(text):
            return Trigger(
                kind=TriggerKind.SENSITIVE_PATH,
                subject=text,
                tier=rule.minimum_tier,
                rule_id=rule.rule_id,
                pattern=rule.pattern,
                detail=rule.rationale,
            )
    return None


@dataclass(frozen=True, slots=True)
class ChangeSet:
    """What is being assessed, stated as facts rather than as a diff.

    There is no field here for file content or a diff hunk.  Findings reference
    paths and evidence digests, and a secret that was found is identified by the
    digest of its location, never by its value — a security report that quotes
    the secret it found has itself become a secret store.
    """

    change_set_id: str
    paths: tuple[str, ...]
    new_external_dependencies: tuple[str, ...] = ()
    public_api_changed: bool = False
    repo_snapshot_sha: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.change_set_id, "change_set.change_set_id")
        if not self.paths:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message="a change set with no paths cannot be assessed",
                recommended_action="list the changed paths",
            )
        for index, path in enumerate(self.paths):
            require_str(path, f"change_set.paths[{index}]", max_length=1024)
        require_bool(self.public_api_changed, "change_set.public_api_changed")

    def to_payload(self) -> dict[str, Any]:
        return {
            "changeSetId": self.change_set_id,
            "paths": list(self.paths),
            "newExternalDependencies": list(self.new_external_dependencies),
            "publicApiChanged": self.public_api_changed,
            "repoSnapshotSha": self.repo_snapshot_sha,
        }


@dataclass(frozen=True, slots=True)
class SecurityPolicy:
    """The floor and the escalation strengths, stated once."""

    baseline_tier: Tier = Tier.T1
    dependency_tier: Tier = Tier.T2
    public_api_tier: Tier = Tier.T2

    def to_payload(self) -> dict[str, Any]:
        return {
            "baselineTier": str(self.baseline_tier),
            "dependencyTier": str(self.dependency_tier),
            "publicApiTier": str(self.public_api_tier),
        }


@dataclass(frozen=True, slots=True)
class TierDerivation:
    """The derived floor plus every trigger that contributed to it."""

    tier: Tier
    triggers: tuple[Trigger, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "tier": str(self.tier),
            "triggers": [item.to_payload() for item in self.triggers],
            "requiredControls": [str(item) for item in controls_for(self.tier)],
        }


def derive_tier(change_set: ChangeSet,
                policy: SecurityPolicy | None = None) -> TierDerivation:
    """Compute the minimum tier this change set demands.

    Every contributing trigger is kept, not just the winning one.  During a
    review the question is never only "why T3" but "what else is in here".
    """

    active = policy or SecurityPolicy()
    triggers: list[Trigger] = [
        Trigger(TriggerKind.BASELINE, change_set.change_set_id, active.baseline_tier,
                detail="baseline assurance for any code change")
    ]
    for path in change_set.paths:
        found = classify_path(path)
        if found is not None:
            triggers.append(found)
    for dependency in change_set.new_external_dependencies:
        triggers.append(Trigger(
            kind=TriggerKind.NEW_EXTERNAL_DEPENDENCY,
            subject=dependency,
            tier=active.dependency_tier,
            detail="a new external dependency adds an unreviewed supply chain edge",
        ))
    if change_set.public_api_changed:
        triggers.append(Trigger(
            kind=TriggerKind.PUBLIC_API_CHANGE,
            subject=change_set.change_set_id,
            tier=active.public_api_tier,
            detail="a public API change widens the attack surface for every consumer",
        ))
    highest = max(triggers, key=lambda item: item.tier.rank).tier
    return TierDerivation(tier=highest, triggers=tuple(triggers))


# --- controls ----------------------------------------------------------------


class ControlMethod(StrEnum):
    """How a control was carried out.

    The distinction exists to enforce one invariant: a model reviewing a diff
    is not a scanner.  ``LLM_REVIEW`` is a real method with real value and it
    cannot satisfy a control that requires deterministic tooling.
    """

    TOOL = "tool"
    LLM_REVIEW = "llm-review"
    HUMAN = "human"


#: Controls that only deterministic tooling can satisfy.
_TOOL_ONLY_CONTROLS: frozenset[Control] = frozenset({
    Control.SECRET_SCAN,
    Control.DEPENDENCY_ADVISORY,
    Control.STATIC_ANALYSIS,
    Control.LICENSE_CHECK,
    Control.PROVENANCE_ATTESTATION,
})


class ControlStatus(StrEnum):
    """Outcome of one control.

    ``MISSING`` and ``ERROR`` are separate from ``FAIL`` because they mean
    different things to the person on the other end: a failed control found
    something, a missing one found nothing because it never ran.
    """

    PASS = "PASS"  # noqa: S105 - a control/verdict name, not a credential
    FAIL = "FAIL"
    MISSING = "MISSING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ControlReport:
    """One control's result, with the method that produced it."""

    control: Control
    status: ControlStatus
    method: ControlMethod
    evidence_ids: tuple[str, ...] = ()
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.control, Control):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown control {self.control!r}",
                recommended_action=f"use one of {sorted(c.value for c in Control)}",
            )
        for index, item in enumerate(self.evidence_ids):
            require_identifier(item, f"control_report.evidence_ids[{index}]")

    @property
    def method_is_sufficient(self) -> bool:
        """A tool-only control is not satisfied by a review."""

        if self.control in _TOOL_ONLY_CONTROLS:
            return self.method is ControlMethod.TOOL
        return True

    def to_payload(self) -> dict[str, Any]:
        return {
            "control": str(self.control),
            "status": str(self.status),
            "method": str(self.method),
            "evidenceIds": list(self.evidence_ids),
            "methodSufficient": self.method_is_sufficient,
            "detail": self.detail,
        }


# --- findings ----------------------------------------------------------------


class Severity(StrEnum):
    """Finding severity, worst first.  ``UNKNOWN`` is not the bottom."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"
    UNKNOWN = "UNKNOWN"


_SEVERITY_RANK: Mapping[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
    Severity.UNKNOWN: 0,
}


class FindingKind(StrEnum):
    """What kind of problem a finding describes."""

    SECRET = "secret"  # noqa: S105 - a control/verdict name, not a credential
    DEPENDENCY = "dependency"
    STATIC = "static"
    LICENSE = "license"
    DATA_FLOW = "data-flow"
    TENANT_ISOLATION = "tenant-isolation"
    PROMPT_INJECTION = "prompt-injection"
    OTHER = "other"


#: Kinds whose severity the kernel sets rather than accepts.  A scanner that
#: reports a leaked credential as "low" is wrong, and a tenant-isolation
#: regression is a P0 by definition of the product.
_FLOORED_KINDS: Mapping[FindingKind, Severity] = {
    FindingKind.SECRET: Severity.CRITICAL,
    FindingKind.TENANT_ISOLATION: Severity.CRITICAL,
    FindingKind.PROMPT_INJECTION: Severity.HIGH,
}

#: Kinds no waiver may cover.  A waiver over these is a waiver over the ability
#: to keep tenants apart or to keep a credential secret, which nobody has the
#: authority to grant.
_UNWAIVABLE_KINDS: frozenset[FindingKind] = frozenset({
    FindingKind.SECRET,
    FindingKind.TENANT_ISOLATION,
})


class FindingStatus(StrEnum):
    """Lifecycle of a finding."""

    OPEN = "OPEN"
    FIXED = "FIXED"
    FALSE_POSITIVE = "FALSE_POSITIVE"

    @property
    def is_resolved(self) -> bool:
        return self in (FindingStatus.FIXED, FindingStatus.FALSE_POSITIVE)


@dataclass(frozen=True, slots=True)
class Finding:
    """A security finding, identified without quoting what it found."""

    finding_id: str
    kind: FindingKind
    severity: Severity
    status: FindingStatus
    control: Control
    location_digest: str = ""
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.finding_id, "finding.finding_id")
        for name, enum_type in (("kind", FindingKind), ("severity", Severity),
                                ("status", FindingStatus), ("control", Control)):
            if not isinstance(getattr(self, name), enum_type):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"finding.{name}={getattr(self, name)!r} is not a known value",
                    recommended_action=f"use a {enum_type.__name__} member",
                )

    @property
    def requires_triage(self) -> bool:
        return self.severity is Severity.UNKNOWN

    @property
    def effective_severity(self) -> Severity:
        """Severity after flooring and after the untriaged rule.

        An unknown severity resolves to ``CRITICAL``.  The opposite convention
        — unknown means informational — is the one that lets an unclassified
        finding ship, and it is chosen surprisingly often because it makes
        dashboards look better.
        """

        floored = _FLOORED_KINDS.get(self.kind)
        if self.severity is Severity.UNKNOWN:
            return Severity.CRITICAL
        if floored is not None and _SEVERITY_RANK[floored] < _SEVERITY_RANK[self.severity]:
            return floored
        return self.severity

    @property
    def is_blocking(self) -> bool:
        return (not self.status.is_resolved
                and _SEVERITY_RANK[self.effective_severity] <= _SEVERITY_RANK[Severity.HIGH])

    @property
    def is_waivable(self) -> bool:
        return self.kind not in _UNWAIVABLE_KINDS

    def to_payload(self) -> dict[str, Any]:
        return {
            "findingId": self.finding_id,
            "kind": str(self.kind),
            "reportedSeverity": str(self.severity),
            "effectiveSeverity": str(self.effective_severity),
            "requiresTriage": self.requires_triage,
            "status": str(self.status),
            "control": str(self.control),
            "locationDigest": self.location_digest,
            "evidenceIds": list(self.evidence_ids),
            "blocking": self.is_blocking,
            "waivable": self.is_waivable,
        }


@dataclass(frozen=True, slots=True)
class Waiver:
    """A named human accepting a named risk until a named time.

    All four of approver, scope, expiry and justification are required.  Each
    missing one has a specific failure mode: anonymous, unbounded, unlimited,
    and unexplained respectively.
    """

    waiver_id: str
    approver: str
    scope: tuple[str, ...]
    expires_at: datetime
    justification: str

    def __post_init__(self) -> None:
        require_identifier(self.waiver_id, "waiver.waiver_id")
        require_str(self.approver, "waiver.approver", max_length=256)
        if not self.scope:
            raise KernelError(
                code="WAIVER_INVALID",
                message=f"waiver {self.waiver_id!r} has an empty scope",
                recommended_action="name the finding ids or control ids the waiver covers",
            )
        for index, item in enumerate(self.scope):
            require_identifier(item, f"waiver.scope[{index}]")
        format_timestamp(self.expires_at)
        if not self.justification or len(self.justification.strip()) < 8:
            raise KernelError(
                code="WAIVER_INVALID",
                message=f"waiver {self.waiver_id!r} has no usable justification",
                recommended_action="state why the risk is acceptable",
            )

    def is_live(self, now: datetime) -> bool:
        """A waiver expiring exactly now has expired."""

        return self.expires_at > now

    def covers(self, subject: str, *, now: datetime) -> bool:
        return subject in self.scope and self.is_live(now)

    def to_payload(self) -> dict[str, Any]:
        return {
            "waiverId": self.waiver_id,
            "approver": self.approver,
            "scope": list(self.scope),
            "expiresAt": format_timestamp(self.expires_at),
            "justification": self.justification,
        }


# --- assessment --------------------------------------------------------------


class SecurityDecision(StrEnum):
    """The gate's verdict.

    ``BLOCKED`` means no verdict could be reached — a control never ran or
    errored — and outranks ``FAIL`` for routing: someone has to make the check
    run before anyone can argue about the result.
    """

    PASS = "PASS"  # noqa: S105 - a control/verdict name, not a credential
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class ReasonCode(StrEnum):
    """Why the gate decided what it decided, one entry per triggered rule."""

    CONTROL_MISSING = "CONTROL_MISSING"
    CONTROL_FAILED = "CONTROL_FAILED"
    CONTROL_ERRORED = "CONTROL_ERRORED"
    CONTROL_METHOD_INSUFFICIENT = "CONTROL_METHOD_INSUFFICIENT"
    BLOCKING_FINDING_OPEN = "BLOCKING_FINDING_OPEN"
    UNTRIAGED_FINDING = "UNTRIAGED_FINDING"
    SECRET_EXPOSED = "SECRET_EXPOSED"  # noqa: S105 - a control/verdict name, not a credential
    TENANT_BOUNDARY_BROKEN = "TENANT_BOUNDARY_BROKEN"
    PROMPT_INJECTION_DETECTED = "PROMPT_INJECTION_DETECTED"
    TIER_ESCALATED = "TIER_ESCALATED"
    WAIVER_APPLIED = "WAIVER_APPLIED"
    WAIVER_EXPIRED = "WAIVER_EXPIRED"
    WAIVER_OUT_OF_SCOPE = "WAIVER_OUT_OF_SCOPE"
    WAIVER_NOT_PERMITTED = "WAIVER_NOT_PERMITTED"


_BLOCKING_REASONS = frozenset({
    ReasonCode.CONTROL_MISSING,
    ReasonCode.CONTROL_ERRORED,
    ReasonCode.CONTROL_METHOD_INSUFFICIENT,
})
_INFORMATIONAL_REASONS = frozenset({
    ReasonCode.TIER_ESCALATED,
    ReasonCode.WAIVER_APPLIED,
})


@dataclass(frozen=True, slots=True)
class Reason:
    """One rule firing against one subject."""

    code: ReasonCode
    subject: str
    detail: str = ""

    @property
    def blocks(self) -> bool:
        return self.code in _BLOCKING_REASONS

    @property
    def fails(self) -> bool:
        return self.code not in _BLOCKING_REASONS and self.code not in _INFORMATIONAL_REASONS

    def to_payload(self) -> dict[str, Any]:
        return {"code": str(self.code), "subject": self.subject, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class AssuranceResult:
    """The full assessment: what was required, what ran, and what is missing."""

    change_set_id: str
    requested_tier: Tier
    derived_tier: Tier
    effective_tier: Tier
    triggers: tuple[Trigger, ...]
    required_controls: tuple[Control, ...]
    controls_passed: tuple[Control, ...]
    controls_failed: tuple[Control, ...]
    controls_missing: tuple[Control, ...]
    control_reports: tuple[ControlReport, ...]
    findings: tuple[Finding, ...]
    blocking_finding_ids: tuple[str, ...]
    waivers_applied: tuple[str, ...]
    waivers_rejected: tuple[tuple[str, str], ...]
    reasons: tuple[Reason, ...]
    decision: SecurityDecision
    assessed_at: datetime

    def reason_codes(self) -> tuple[str, ...]:
        return tuple(str(item.code) for item in self.reasons)

    def to_payload(self) -> dict[str, Any]:
        return {
            "changeSetId": self.change_set_id,
            "requestedTier": str(self.requested_tier),
            "derivedTier": str(self.derived_tier),
            "effectiveTier": str(self.effective_tier),
            "tierEscalated": self.effective_tier.rank > self.requested_tier.rank,
            "triggers": [item.to_payload() for item in self.triggers],
            "requiredControls": [str(item) for item in self.required_controls],
            "controlsPassed": [str(item) for item in self.controls_passed],
            "controlsFailed": [str(item) for item in self.controls_failed],
            "controlsMissing": [str(item) for item in self.controls_missing],
            "controlReports": [item.to_payload() for item in self.control_reports],
            "findings": [item.to_payload() for item in self.findings],
            "blockingFindingIds": list(self.blocking_finding_ids),
            "waiversApplied": list(self.waivers_applied),
            "waiversRejected": [[waiver, reason] for waiver, reason in self.waivers_rejected],
            "reasons": [item.to_payload() for item in self.reasons],
            "decision": str(self.decision),
            "assessedAt": format_timestamp(self.assessed_at),
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


def assess(change_set: ChangeSet, tier: Tier, findings: Sequence[Finding], *,
           control_reports: Sequence[ControlReport] = (),
           waivers: Sequence[Waiver] = (),
           policy: SecurityPolicy | None = None,
           now: datetime) -> AssuranceResult:
    """Assess a change set at the higher of the requested and the derived tier.

    Nothing here is satisfied by silence.  Every required control is looked up
    by name; a control with no report is ``MISSING`` and blocks, a control
    reported by an insufficient method is treated as if it had not run, and a
    finding that nobody has triaged blocks at ``CRITICAL``.
    """

    if not isinstance(tier, Tier):
        raise KernelError(
            code="ASSURANCE_TIER_UNKNOWN",
            message=f"unknown assurance tier {tier!r}",
            recommended_action=f"use one of {[item.value for item in _TIER_ORDER]}",
        )
    derivation = derive_tier(change_set, policy)
    effective = tier if tier.rank >= derivation.tier.rank else derivation.tier
    required = controls_for(effective)
    reasons: list[Reason] = []

    if effective.rank > tier.rank:
        escalating = [item for item in derivation.triggers if item.tier is derivation.tier]
        reasons.append(Reason(
            ReasonCode.TIER_ESCALATED,
            change_set.change_set_id,
            f"requested {tier}, change set requires {effective} via "
            + ", ".join(sorted(item.rule_id or str(item.kind) for item in escalating)),
        ))

    by_control: dict[Control, ControlReport] = {}
    for report in control_reports:
        by_control[report.control] = report

    passed: list[Control] = []
    failed: list[Control] = []
    missing: list[Control] = []
    for control in required:
        report = by_control.get(control)
        if report is None:
            missing.append(control)
            reasons.append(Reason(ReasonCode.CONTROL_MISSING, str(control),
                                  f"{control} is required at {effective} and did not run"))
            continue
        if not report.method_is_sufficient:
            missing.append(control)
            reasons.append(Reason(
                ReasonCode.CONTROL_METHOD_INSUFFICIENT, str(control),
                f"{control} was reported by {report.method}; this control requires tooling",
            ))
            continue
        if report.status is ControlStatus.PASS:
            passed.append(control)
        elif report.status is ControlStatus.FAIL:
            failed.append(control)
            reasons.append(Reason(ReasonCode.CONTROL_FAILED, str(control), report.detail))
        elif report.status is ControlStatus.ERROR:
            missing.append(control)
            reasons.append(Reason(ReasonCode.CONTROL_ERRORED, str(control), report.detail))
        else:
            missing.append(control)
            reasons.append(Reason(ReasonCode.CONTROL_MISSING, str(control),
                                  "reported as MISSING by the runner"))

    applied: list[str] = []
    rejected: list[tuple[str, str]] = []
    blocking: list[str] = []
    for finding in findings:
        if not finding.is_blocking:
            continue
        waiver = _live_waiver_for(finding.finding_id, waivers, now=now)
        if waiver is not None and not finding.is_waivable:
            rejected.append((waiver.waiver_id, str(ReasonCode.WAIVER_NOT_PERMITTED)))
            reasons.append(Reason(ReasonCode.WAIVER_NOT_PERMITTED, finding.finding_id,
                                  f"a {finding.kind} finding cannot be waived"))
            waiver = None
        if waiver is not None:
            applied.append(waiver.waiver_id)
            reasons.append(Reason(ReasonCode.WAIVER_APPLIED, finding.finding_id,
                                  f"waived by {waiver.approver} until "
                                  f"{format_timestamp(waiver.expires_at)}"))
            continue
        for candidate in waivers:
            if finding.finding_id in candidate.scope and not candidate.is_live(now):
                rejected.append((candidate.waiver_id, str(ReasonCode.WAIVER_EXPIRED)))
                reasons.append(Reason(ReasonCode.WAIVER_EXPIRED, finding.finding_id,
                                      f"waiver {candidate.waiver_id} expired at "
                                      f"{format_timestamp(candidate.expires_at)}"))
        blocking.append(finding.finding_id)
        reasons.append(_finding_reason(finding))
        if finding.requires_triage:
            reasons.append(Reason(ReasonCode.UNTRIAGED_FINDING, finding.finding_id,
                                  "severity is unknown; treated as CRITICAL until triaged"))

    for waiver in waivers:
        known = {finding.finding_id for finding in findings}
        out_of_scope = sorted(set(waiver.scope) - known)
        if out_of_scope and waiver.waiver_id not in applied:
            rejected.append((waiver.waiver_id, str(ReasonCode.WAIVER_OUT_OF_SCOPE)))
            reasons.append(Reason(ReasonCode.WAIVER_OUT_OF_SCOPE, waiver.waiver_id,
                                  f"scope names unknown subjects {out_of_scope}"))

    if any(reason.blocks for reason in reasons):
        decision = SecurityDecision.BLOCKED
    elif any(reason.fails for reason in reasons):
        decision = SecurityDecision.FAIL
    else:
        decision = SecurityDecision.PASS

    return AssuranceResult(
        change_set_id=change_set.change_set_id,
        requested_tier=tier,
        derived_tier=derivation.tier,
        effective_tier=effective,
        triggers=derivation.triggers,
        required_controls=required,
        controls_passed=tuple(passed),
        controls_failed=tuple(failed),
        controls_missing=tuple(missing),
        control_reports=tuple(sorted(control_reports, key=lambda item: str(item.control))),
        findings=tuple(findings),
        blocking_finding_ids=tuple(blocking),
        waivers_applied=tuple(sorted(set(applied))),
        waivers_rejected=tuple(sorted(set(rejected))),
        reasons=tuple(reasons),
        decision=decision,
        assessed_at=now,
    )


def _live_waiver_for(subject: str, waivers: Sequence[Waiver], *,
                     now: datetime) -> Waiver | None:
    for waiver in waivers:
        if waiver.covers(subject, now=now):
            return waiver
    return None


def _finding_reason(finding: Finding) -> Reason:
    if finding.kind is FindingKind.SECRET:
        return Reason(ReasonCode.SECRET_EXPOSED, finding.finding_id,
                      "a credential is present in the change set")
    if finding.kind is FindingKind.TENANT_ISOLATION:
        return Reason(ReasonCode.TENANT_BOUNDARY_BROKEN, finding.finding_id,
                      "a tenant isolation regression is a P0 by definition")
    if finding.kind is FindingKind.PROMPT_INJECTION:
        return Reason(ReasonCode.PROMPT_INJECTION_DETECTED, finding.finding_id,
                      "untrusted repository text reached an instruction position")
    return Reason(ReasonCode.BLOCKING_FINDING_OPEN, finding.finding_id,
                  f"open {finding.effective_severity} finding from {finding.control}")


# --- durable record ----------------------------------------------------------


def record_assessment(result: AssuranceResult, events: EventStore, *, stream_id: str,
                      fencing_token: int) -> Mapping[str, Any]:
    """Append an assessment to the run log, idempotently and behind a fence."""

    event = events.append(
        stream_id,
        {"kind": "security.assessment", "assessment": result.to_payload(),
         "assessmentDigest": result.digest},
        idempotency_key=result.digest,
        fencing_token=fencing_token,
    )
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "assessmentDigest": result.digest,
    }


# --- registry entry point ----------------------------------------------------


def _decode_enum(value: Any, enum_type: type[StrEnum], field_name: str) -> Any:
    text = require_str(value, field_name, max_length=64)
    if text not in {item.value for item in enum_type}:
        raise KernelError(
            code="MALFORMED_INPUT",
            message=f"unknown {field_name} {text!r}",
            recommended_action=f"use one of {sorted(item.value for item in enum_type)}",
        )
    return enum_type(text)


def _decode_tier(value: Any, field_name: str) -> Tier:
    text = require_str(value, field_name, max_length=8)
    if text not in {item.value for item in Tier}:
        raise KernelError(
            code="ASSURANCE_TIER_UNKNOWN",
            message=f"unknown assurance tier {text!r}",
            recommended_action=f"use one of {[item.value for item in _TIER_ORDER]}",
        )
    return Tier(text)


def _decode_finding(payload: Mapping[str, Any]) -> Finding:
    reject_unknown_fields(
        payload,
        {"findingId", "kind", "severity", "status", "control", "locationDigest", "evidenceIds"},
        field_name="finding",
    )
    return Finding(
        finding_id=require_identifier(payload.get("findingId"), "finding.findingId"),
        kind=_decode_enum(payload.get("kind"), FindingKind, "finding.kind"),
        severity=_decode_enum(payload.get("severity"), Severity, "finding.severity"),
        status=_decode_enum(payload.get("status"), FindingStatus, "finding.status"),
        control=_decode_enum(payload.get("control"), Control, "finding.control"),
        location_digest=str(payload.get("locationDigest", "")),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()), "finding.evidenceIds"),
    )


def _decode_control_report(payload: Mapping[str, Any]) -> ControlReport:
    reject_unknown_fields(payload, {"control", "status", "method", "evidenceIds", "detail"},
                          field_name="control report")
    return ControlReport(
        control=_decode_enum(payload.get("control"), Control, "controlReport.control"),
        status=_decode_enum(payload.get("status"), ControlStatus, "controlReport.status"),
        method=_decode_enum(payload.get("method"), ControlMethod, "controlReport.method"),
        evidence_ids=require_str_seq(payload.get("evidenceIds", ()),
                                     "controlReport.evidenceIds"),
        detail=str(payload.get("detail", "")),
    )


def _decode_waiver(payload: Mapping[str, Any]) -> Waiver:
    reject_unknown_fields(payload, {"waiverId", "approver", "scope", "expiresAt",
                                    "justification"}, field_name="waiver")
    return Waiver(
        waiver_id=require_identifier(payload.get("waiverId"), "waiver.waiverId"),
        approver=require_str(payload.get("approver"), "waiver.approver", max_length=256),
        scope=require_str_seq(payload.get("scope", ()), "waiver.scope", allow_empty=False),
        expires_at=parse_timestamp(payload.get("expiresAt"), "waiver.expiresAt"),
        justification=require_str(payload.get("justification"), "waiver.justification"),
    )


def _threat_model_delta(result: AssuranceResult) -> dict[str, Any]:
    categories = sorted({
        item.rule_id.split("-")[0] for item in result.triggers
        if item.kind is TriggerKind.SENSITIVE_PATH
    })
    return {
        "changeSetId": result.change_set_id,
        "surfacesTouched": categories,
        "newSupplyChainEdges": [
            item.subject for item in result.triggers
            if item.kind is TriggerKind.NEW_EXTERNAL_DEPENDENCY
        ],
        "publicApiWidened": any(item.kind is TriggerKind.PUBLIC_API_CHANGE
                                for item in result.triggers),
        "tierMovedFrom": str(result.requested_tier),
        "tierMovedTo": str(result.effective_tier),
    }


@register("tiered-security-assurance")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    A failing or blocked gate raises ``SECURITY_GATE_FAILED`` carrying the whole
    assessment in ``details``.  It is not returned as a successful skill run
    with a sad payload, because a caller reading ``status == SUCCEEDED`` would
    conclude the change is safe to ship.
    """

    reject_unknown_fields(
        request,
        {"change_set", "assurance_tier", "findings", "control_reports", "waivers",
         "security_policy", "assessed_at", "repo_snapshot_sha"},
        field_name="tiered-security-assurance request",
    )
    change_payload = require_mapping(request.get("change_set"), "change_set")
    reject_unknown_fields(
        change_payload,
        {"changeSetId", "paths", "newExternalDependencies", "publicApiChanged",
         "repoSnapshotSha"},
        field_name="change_set",
    )
    change_set = ChangeSet(
        change_set_id=require_identifier(change_payload.get("changeSetId"),
                                         "change_set.changeSetId"),
        paths=require_str_seq(change_payload.get("paths", ()), "change_set.paths",
                              allow_empty=False),
        new_external_dependencies=require_str_seq(
            change_payload.get("newExternalDependencies", ()),
            "change_set.newExternalDependencies"),
        public_api_changed=require_bool(change_payload.get("publicApiChanged", False),
                                        "change_set.publicApiChanged"),
        repo_snapshot_sha=str(change_payload.get("repoSnapshotSha", "")),
    )

    live_snapshot = request.get("repo_snapshot_sha")
    if live_snapshot is not None:
        expected = require_str(live_snapshot, "repo_snapshot_sha", max_length=256)
        if change_set.repo_snapshot_sha and change_set.repo_snapshot_sha != expected:
            raise KernelError(
                code="STALE_SNAPSHOT",
                message=(
                    f"change set {change_set.change_set_id} was produced against "
                    f"{change_set.repo_snapshot_sha}, the live snapshot is {expected}"
                ),
                retryable=False,
                recommended_action="re-derive the change set against the live snapshot",
            )

    policy_payload = require_mapping(request.get("security_policy", {}), "security_policy")
    reject_unknown_fields(policy_payload, {"baselineTier", "dependencyTier", "publicApiTier"},
                          field_name="security_policy")
    policy = SecurityPolicy(
        baseline_tier=_decode_tier(policy_payload.get("baselineTier", "T1"),
                                   "security_policy.baselineTier"),
        dependency_tier=_decode_tier(policy_payload.get("dependencyTier", "T2"),
                                     "security_policy.dependencyTier"),
        public_api_tier=_decode_tier(policy_payload.get("publicApiTier", "T2"),
                                     "security_policy.publicApiTier"),
    )

    result = assess(
        change_set,
        _decode_tier(request.get("assurance_tier"), "assurance_tier"),
        tuple(_decode_finding(require_mapping(item, "findings[]"))
              for item in request.get("findings", ())),
        control_reports=tuple(_decode_control_report(require_mapping(item, "control_reports[]"))
                              for item in request.get("control_reports", ())),
        waivers=tuple(_decode_waiver(require_mapping(item, "waivers[]"))
                      for item in request.get("waivers", ())),
        policy=policy,
        now=parse_timestamp(request.get("assessed_at"), "assessed_at"),
    )

    payload = result.to_payload()
    if result.decision is not SecurityDecision.PASS:
        raise KernelError(
            code="SECURITY_GATE_FAILED",
            message=(
                f"security gate {result.decision} for {result.change_set_id} at "
                f"{result.effective_tier}: " + "; ".join(sorted(set(result.reason_codes())))
            ),
            retryable=False,
            evidence_ids=tuple(sorted({
                item for report in result.control_reports for item in report.evidence_ids
            })),
            recommended_action="run the missing controls and resolve the blocking findings",
            details={"assuranceResult": payload, "assessmentDigest": result.digest},
        )

    return {
        "assurance_result": payload,
        "security_gate": {
            "decision": str(result.decision),
            "effectiveTier": str(result.effective_tier),
            "requiredControls": [str(item) for item in result.required_controls],
            "assessmentDigest": result.digest,
        },
        "required_controls": [str(item) for item in result.required_controls],
        "security_findings": [item.to_payload() for item in result.findings],
        "threat_model_delta": _threat_model_delta(result),
        "sbom_references": sorted({
            item for report in result.control_reports
            if report.control in (Control.DEPENDENCY_ADVISORY, Control.LICENSE_CHECK)
            for item in report.evidence_ids
        }),
        "waiver": {
            "applied": list(result.waivers_applied),
            "rejected": [[waiver, reason] for waiver, reason in result.waivers_rejected],
        },
        "evidenceIds": sorted({
            item for report in result.control_reports for item in report.evidence_ids
        }),
    }
