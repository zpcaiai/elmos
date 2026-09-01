"""Policy Hook Kernel.

Hooks decide what may happen at the moments that matter — before a tool call, before a write,
before the network, before a release, before a model call.  Three properties make this component
either trustworthy or theatre:

*The empty decision set is DENY.*  "No rule objected" is not permission.  Almost every policy
engine that has been quietly bypassed in production was bypassed by arranging for zero rules to
match, so :func:`aggregate` treats an empty input as ``DENY`` and every path that produces no
match reaches that same function.

*Predicates are data, never code.*  A rule is a small typed matcher over subject fields —
``equals``, ``in``, ``prefix``, ``glob-path`` and numeric ``gte``/``lte``.  There is no ``eval``,
no expression string, no callable loaded from configuration.  A policy file is thus a value that
can be hashed, diffed, signed and replayed, and a malicious policy file is a bad decision rather
than remote code execution.

*Obligations survive the decision.*  ``redact-secrets`` and ``record-second-review`` are not
advice; they are inputs to a later gate.  They ride on the outcome, they are returned to the
caller in a deterministic order, and they are collected from *every* matched rule — including
``ALLOW`` rules, because "allowed, but redact the secrets" is the common case and dropping the
second clause is a security hole rather than a formatting choice.

Two supporting decisions worth stating.  A rule that references a subject field the subject does
not carry raises ``MISSING_REQUIRED_INPUT`` instead of quietly not matching: silently skipping a
DENY rule because its input was absent is precisely the failure this kernel exists to prevent, so
the rules at a hook point define the required shape of a subject at that hook point.  And a type
mismatch discovered during evaluation (a numeric threshold against a non-numeric field) raises
``POLICY_ENGINE_ERROR`` rather than evaluating to ``False`` — a policy engine that errors must
fail closed, and ``False`` is not closed.

``handle`` returns a DENY decision as a *successful* skill result rather than raising.  The
kernel's product is the decision plus its evidence; raising would discard the obligations and the
rule trace, which are exactly what the caller needs in order to deny correctly.  Callers wanting
enforcement call :meth:`PolicyOutcome.raise_for_decision`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from .contracts import (
    digest,
    format_timestamp,
    parse_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .registry import register

__all__ = [
    "ApprovalRequest",
    "Decision",
    "HOOK_POINTS",
    "Match",
    "OPS",
    "PolicyOutcome",
    "PolicyRule",
    "PolicySnapshot",
    "RuleTrace",
    "aggregate",
    "explain",
    "handle",
]

register_codes(Category.POLICY, "POLICY_ENGINE_ERROR", "APPROVAL_REQUIRED", "APPROVAL_EXPIRED")


class Decision(StrEnum):
    """Hook decisions, declared most restrictive first.

    The declaration order *is* the precedence order; :data:`PRECEDENCE` freezes it so that adding
    a member cannot silently reorder aggregation.
    """

    DENY = "DENY"
    ASK_USER = "ASK_USER"
    REQUIRE_ESCALATION = "REQUIRE_ESCALATION"
    REQUIRE_SECOND_REVIEW = "REQUIRE_SECOND_REVIEW"
    MODIFY_INPUT = "MODIFY_INPUT"
    ALLOW = "ALLOW"


#: Most restrictive first.  ``aggregate`` returns the earliest member present.
PRECEDENCE: tuple[Decision, ...] = (
    Decision.DENY,
    Decision.ASK_USER,
    Decision.REQUIRE_ESCALATION,
    Decision.REQUIRE_SECOND_REVIEW,
    Decision.MODIFY_INPUT,
    Decision.ALLOW,
)
_RANK: dict[Decision, int] = {member: index for index, member in enumerate(PRECEDENCE)}

if set(PRECEDENCE) != set(Decision):  # pragma: no cover - guards a future edit
    raise RuntimeError("PRECEDENCE must rank every Decision member")

#: Hook points the kernel understands.  An unknown hook point is refused, not defaulted.
HOOK_POINTS: tuple[str, ...] = (
    "pre-tool-call",
    "pre-write",
    "pre-network",
    "pre-release",
    "pre-model-call",
)

#: Supported match operators.  This list is the whole expression language, on purpose.
OPS: tuple[str, ...] = ("equals", "in", "prefix", "glob-path", "gte", "lte")

#: Decisions that cannot proceed without a human or a second party.
APPROVAL_DECISIONS: tuple[Decision, ...] = (
    Decision.ASK_USER,
    Decision.REQUIRE_ESCALATION,
    Decision.REQUIRE_SECOND_REVIEW,
)


def aggregate(decisions: Iterable[Decision]) -> Decision:
    """Return the most restrictive decision present; an empty set is ``DENY``.

    Fail-closed is the entire point of this function.  "Nothing matched" and "everything allowed"
    must never be the same answer.
    """

    most_restrictive: Decision | None = None
    for decision in decisions:
        if not isinstance(decision, Decision):
            raise KernelError(
                code="POLICY_ENGINE_ERROR",
                message=f"{decision!r} is not a Decision",
                recommended_action="treat as a policy engine defect and deny",
            )
        if most_restrictive is None or _RANK[decision] < _RANK[most_restrictive]:
            most_restrictive = decision
    return Decision.DENY if most_restrictive is None else most_restrictive


# --- matching ----------------------------------------------------------------


def _as_number(value: Any, *, where: str) -> Decimal:
    """Coerce a comparable quantity, refusing floats.

    Quantities travel as integers or decimal strings so that two parties agree on the value; a
    float would make the same policy decide differently on two machines.
    """

    if isinstance(value, bool) or isinstance(value, float):
        raise KernelError(
            code="POLICY_ENGINE_ERROR",
            message=f"{where} must be an integer or decimal string, not {type(value).__name__}",
            recommended_action="send the quantity as an integer or a decimal string",
        )
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            parsed = Decimal(value)
        except InvalidOperation as exc:
            raise KernelError(
                code="POLICY_ENGINE_ERROR",
                message=f"{where}={value!r} is not a decimal",
                recommended_action="supply a numeric threshold value",
            ) from exc
        if not parsed.is_finite():
            raise KernelError(
                code="POLICY_ENGINE_ERROR",
                message=f"{where}={value!r} is not finite",
                recommended_action="supply a finite quantity",
            )
        return parsed
    raise KernelError(
        code="POLICY_ENGINE_ERROR",
        message=f"{where} of type {type(value).__name__} is not comparable",
        recommended_action="treat as a policy engine defect and deny",
    )


def path_glob(pattern: str, path: str) -> bool:
    """Match a ``/``-separated path against a glob, segment by segment.

    ``*`` and ``?`` never cross a ``/``; ``**`` matches any number of segments.  ``fnmatch`` is
    not used because its ``*`` happily spans separators, which turns ``src/*`` into a grant over
    the whole tree — a difference that only shows up as an incident.
    """

    pattern_parts = [part for part in pattern.split("/") if part not in ("", ".")]
    path_parts = [part for part in path.split("/") if part not in ("", ".")]
    return _glob_segments(tuple(pattern_parts), tuple(path_parts))


def _glob_segments(pattern: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    if not pattern:
        return not parts
    head = pattern[0]
    if head == "**":
        for index in range(len(parts) + 1):
            if _glob_segments(pattern[1:], parts[index:]):
                return True
        return False
    if not parts:
        return False
    return _glob_one(head, parts[0]) and _glob_segments(pattern[1:], parts[1:])


def _glob_one(pattern: str, segment: str) -> bool:
    """``*``/``?`` matching inside a single path segment."""

    if not pattern:
        return not segment
    if pattern[0] == "*":
        for index in range(len(segment) + 1):
            if _glob_one(pattern[1:], segment[index:]):
                return True
        return False
    if not segment:
        return False
    if pattern[0] == "?" or pattern[0] == segment[0]:
        return _glob_one(pattern[1:], segment[1:])
    return False


@dataclass(frozen=True, slots=True)
class Match:
    """One typed assertion about one subject field.

    There is no operator that takes an expression, a regular expression or a callable.  Everything
    a rule can say is expressible as ``(field, op, value)``, which is what makes a policy snapshot
    hashable and a policy file safe to accept from a repository.
    """

    field: str
    op: str
    value: Any

    def __post_init__(self) -> None:
        require_identifier(self.field, "match.field")
        if self.op not in OPS:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown match operator {self.op!r}; supported: {list(OPS)}",
                recommended_action="use one of the supported data-driven operators",
                details={"supported": list(OPS)},
            )
        if self.op == "in":
            if isinstance(self.value, (str, bytes)) or not isinstance(self.value, Sequence):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message="match op 'in' requires an array of scalars",
                    recommended_action="supply the membership set as a JSON array",
                )
            object.__setattr__(self, "value", tuple(self.value))
        elif self.op in ("prefix", "glob-path"):
            require_str(self.value, f"match.value for op {self.op}")
        elif self.op in ("gte", "lte"):
            object.__setattr__(self, "value", _as_number(self.value, where="match.value"))
        elif isinstance(self.value, float):
            raise KernelError(
                code="MALFORMED_INPUT",
                message="match values must not be floats",
                recommended_action="use an integer, a decimal string or a plain string",
            )

    def evaluate(self, subject: Mapping[str, Any]) -> bool:
        """Test the assertion.  A type mismatch raises rather than returning ``False``."""

        if self.field not in subject:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=(
                    f"subject has no field {self.field!r}; a rule that cannot see its input "
                    "must not be treated as not matching"
                ),
                recommended_action=f"include {self.field!r} in the subject (null is allowed)",
                details={"field": self.field},
            )
        actual = subject[self.field]
        if self.op == "equals":
            return actual == self.value
        if self.op == "in":
            return actual in self.value
        if self.op == "prefix":
            if not isinstance(actual, str):
                raise self._type_error(actual, "a string")
            return actual.startswith(self.value)
        if self.op == "glob-path":
            if not isinstance(actual, str):
                raise self._type_error(actual, "a path string")
            return path_glob(self.value, actual)
        left = _as_number(actual, where=f"subject.{self.field}")
        return left >= self.value if self.op == "gte" else left <= self.value

    def _type_error(self, actual: Any, expected: str) -> KernelError:
        return KernelError(
            code="POLICY_ENGINE_ERROR",
            message=(
                f"subject.{self.field} is {type(actual).__name__}, but op {self.op!r} needs "
                f"{expected}"
            ),
            recommended_action="fix the subject or the rule; a mistyped rule must not allow",
        )

    def to_payload(self) -> dict[str, Any]:
        value: Any = self.value
        if isinstance(value, tuple):
            value = list(value)
        return {"field": self.field, "op": self.op, "value": value}


@dataclass(frozen=True, slots=True)
class PolicyRule:
    """One rule: where it applies, when it fires, what it decides, and what it obliges.

    ``matches`` are ANDed.  There is no OR operator; two rules express a disjunction, and that
    keeps the trace readable — every fired rule names itself in the audit record.
    """

    rule_id: str
    hook_point: str
    matches: tuple[Match, ...]
    decision: Decision
    obligations: tuple[str, ...] = ()
    explanation: str = ""

    def __post_init__(self) -> None:
        require_identifier(self.rule_id, "rule_id")
        if self.hook_point not in HOOK_POINTS:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown hook point {self.hook_point!r}; known: {list(HOOK_POINTS)}",
                recommended_action="bind the rule to a supported hook point",
                details={"known": list(HOOK_POINTS)},
            )
        if not isinstance(self.decision, Decision):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"rule {self.rule_id!r} has a non-Decision decision",
                recommended_action="use a Decision member",
            )
        object.__setattr__(self, "matches", tuple(self.matches))
        object.__setattr__(self, "obligations", tuple(
            require_identifier(item, f"{self.rule_id}.obligations[{index}]")
            for index, item in enumerate(self.obligations)
        ))
        if not self.explanation:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"rule {self.rule_id!r} has no explanation",
                recommended_action="state, in one sentence, why the rule exists",
            )

    @property
    def referenced_fields(self) -> tuple[str, ...]:
        return tuple(sorted({match.field for match in self.matches}))

    def to_payload(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "hookPoint": self.hook_point,
            "match": [match.to_payload() for match in self.matches],
            "decision": str(self.decision),
            "obligations": list(self.obligations),
            "explanation": self.explanation,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], *, where: str) -> PolicyRule:
        body = require_mapping(payload, where)
        reject_unknown_fields(
            body, ("ruleId", "hookPoint", "match", "decision", "obligations", "explanation"),
            field_name=where,
        )
        raw_matches = body.get("match", ())
        if isinstance(raw_matches, (str, bytes)) or not isinstance(raw_matches, Sequence):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{where}.match must be an array",
                recommended_action="supply match as a JSON array of {field, op, value}",
            )
        matches = []
        for index, raw in enumerate(raw_matches):
            item = require_mapping(raw, f"{where}.match[{index}]")
            reject_unknown_fields(item, ("field", "op", "value"),
                                  field_name=f"{where}.match[{index}]")
            matches.append(Match(
                field=require_str(item.get("field"), f"{where}.match[{index}].field"),
                op=require_str(item.get("op"), f"{where}.match[{index}].op", max_length=32),
                value=item.get("value"),
            ))
        decision_text = require_str(body.get("decision"), f"{where}.decision", max_length=32)
        if decision_text not in Decision.__members__:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{where}.decision={decision_text!r} is not a known decision",
                recommended_action=f"use one of {[str(item) for item in PRECEDENCE]}",
            )
        return cls(
            rule_id=require_identifier(body.get("ruleId"), f"{where}.ruleId"),
            hook_point=require_str(body.get("hookPoint"), f"{where}.hookPoint", max_length=64),
            matches=tuple(matches),
            decision=Decision[decision_text],
            obligations=require_str_seq(body.get("obligations", ()), f"{where}.obligations"),
            explanation=require_str(body.get("explanation"), f"{where}.explanation"),
        )


@dataclass(frozen=True, slots=True)
class RuleTrace:
    """One rule's contribution to one decision, whether or not it fired."""

    rule_id: str
    matched: bool
    decision: Decision
    obligations: tuple[str, ...]
    explanation: str
    detail: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "ruleId": self.rule_id,
            "matched": self.matched,
            "decision": str(self.decision),
            "obligations": list(self.obligations),
            "explanation": self.explanation,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """An immutable, content-addressed set of rules.

    ``snapshot_hash`` is computed from the rules themselves, so two snapshots are the same
    snapshot exactly when they decide the same way.  A caller must declare the hash it believes
    it is evaluating against; a mismatch is ``STALE_POLICY_SNAPSHOT``, never a silent refresh.
    """

    snapshot_id: str
    rules: tuple[PolicyRule, ...]
    snapshot_hash: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        require_identifier(self.snapshot_id, "snapshot_id")
        object.__setattr__(self, "rules", tuple(self.rules))
        seen: set[str] = set()
        for rule in self.rules:
            if not isinstance(rule, PolicyRule):
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message="policy snapshot accepts PolicyRule instances only",
                    recommended_action="decode rules with PolicyRule.from_mapping",
                )
            if rule.rule_id in seen:
                raise KernelError(
                    code="MALFORMED_INPUT",
                    message=f"duplicate rule id {rule.rule_id!r} in snapshot",
                    recommended_action="rule ids must be unique across every policy layer",
                )
            seen.add(rule.rule_id)
        object.__setattr__(self, "snapshot_hash", digest({
            "snapshotId": self.snapshot_id,
            "rules": [rule.to_payload() for rule in self.rules],
        }))

    def rules_for(self, hook_point: str) -> tuple[PolicyRule, ...]:
        return tuple(rule for rule in self.rules if rule.hook_point == hook_point)

    def to_payload(self) -> dict[str, Any]:
        return {
            "snapshotId": self.snapshot_id,
            "rules": [rule.to_payload() for rule in self.rules],
            "snapshotHash": self.snapshot_hash,
        }

    def evaluate(self, hook_point: str, subject: Mapping[str, Any], *,
                 declared_snapshot_hash: str) -> PolicyOutcome:
        """Decide one subject at one hook point.

        Rules are evaluated in declaration order (platform layers first, run-local last) so the
        trace reads the way the policy was written.  Order does not affect the verdict —
        aggregation is order independent — but it does affect how quickly a human understands it.
        """

        if hook_point not in HOOK_POINTS:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown hook point {hook_point!r}; known: {list(HOOK_POINTS)}",
                recommended_action="evaluate at a supported hook point",
                details={"known": list(HOOK_POINTS)},
            )
        declared = require_str(declared_snapshot_hash, "declared_snapshot_hash")
        if declared != self.snapshot_hash:
            raise KernelError(
                code="STALE_POLICY_SNAPSHOT",
                message=(
                    f"caller declared policy snapshot {declared} but this snapshot is "
                    f"{self.snapshot_hash}"
                ),
                retryable=False,
                recommended_action="re-read the policy snapshot and re-plan; do not auto-refresh",
                details={"declared": declared, "actual": self.snapshot_hash},
            )
        body = require_mapping(subject, "subject")

        traces: list[RuleTrace] = []
        matched_decisions: list[Decision] = []
        obligations: list[str] = []
        matched_ids: list[str] = []
        for rule in self.rules_for(hook_point):
            failing: str = ""
            matched = True
            for match in rule.matches:
                if not match.evaluate(body):
                    matched = False
                    failing = f"{match.field} {match.op} {match.to_payload()['value']!r}"
                    break
            if matched:
                matched_decisions.append(rule.decision)
                matched_ids.append(rule.rule_id)
                for obligation in rule.obligations:
                    if obligation not in obligations:
                        obligations.append(obligation)
                detail = "all matches satisfied" if rule.matches else "unconditional rule"
            else:
                detail = f"did not match: {failing}"
            traces.append(RuleTrace(
                rule_id=rule.rule_id,
                matched=matched,
                decision=rule.decision,
                obligations=rule.obligations,
                explanation=rule.explanation,
                detail=detail,
            ))

        decision = aggregate(matched_decisions)
        if not matched_decisions:
            traces.append(RuleTrace(
                rule_id="fail-closed",
                matched=True,
                decision=Decision.DENY,
                obligations=(),
                explanation="no rule matched this subject at this hook point",
                detail="an empty decision set is a deny, never an allow",
            ))
        return PolicyOutcome(
            hook_point=hook_point,
            decision=decision,
            obligations=tuple(obligations),
            policy_snapshot_hash=self.snapshot_hash,
            subject_digest=digest(dict(body)),
            trace=tuple(traces),
            matched_rule_ids=tuple(matched_ids),
            evaluated_rule_count=len(self.rules_for(hook_point)),
        )


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    """A decision, its obligations, and the ordered trace that produced both."""

    hook_point: str
    decision: Decision
    obligations: tuple[str, ...]
    policy_snapshot_hash: str
    subject_digest: str
    trace: tuple[RuleTrace, ...]
    matched_rule_ids: tuple[str, ...]
    evaluated_rule_count: int

    def __post_init__(self) -> None:
        if not self.trace:
            raise KernelError(
                code="POLICY_ENGINE_ERROR",
                message="a policy outcome without a trace is not auditable",
                recommended_action="treat as a policy engine defect and deny",
            )
        if self.decision is Decision.ALLOW and not self.matched_rule_ids:
            raise KernelError(
                code="POLICY_ENGINE_ERROR",
                message="ALLOW without a matched rule is an unexplainable allow",
                recommended_action="treat as a policy engine defect and deny",
            )

    @property
    def requires_approval(self) -> bool:
        return self.decision in APPROVAL_DECISIONS

    def raise_for_decision(self) -> None:
        """Enforce the decision by raising, for callers that want a gate rather than a verdict."""

        if self.decision is Decision.ALLOW or self.decision is Decision.MODIFY_INPUT:
            return
        code = {
            Decision.DENY: "POLICY_DENIED",
            Decision.ASK_USER: "APPROVAL_REQUIRED",
            Decision.REQUIRE_ESCALATION: "POLICY_REQUIRES_APPROVAL",
            Decision.REQUIRE_SECOND_REVIEW: "POLICY_REQUIRES_APPROVAL",
        }[self.decision]
        raise KernelError(
            code=code,
            message=f"{self.hook_point}: policy decided {self.decision}",
            retryable=False,
            recommended_action=(
                "obtain the required approval and re-evaluate against the same snapshot"
            ),
            details={"decision": str(self.decision),
                     "obligations": list(self.obligations),
                     "policySnapshotHash": self.policy_snapshot_hash,
                     "matchedRuleIds": list(self.matched_rule_ids)},
        )

    def to_payload(self) -> dict[str, Any]:
        core = {
            "hookPoint": self.hook_point,
            "decision": str(self.decision),
            "obligations": list(self.obligations),
            "policySnapshotHash": self.policy_snapshot_hash,
            "subjectDigest": self.subject_digest,
            "matchedRuleIds": list(self.matched_rule_ids),
            "evaluatedRuleCount": self.evaluated_rule_count,
            "trace": [item.to_payload() for item in self.trace],
        }
        return {**core, "digest": digest(core)}


def explain(outcome: PolicyOutcome) -> tuple[str, ...]:
    """Render the ordered rule trace as one line per rule, ending with the verdict.

    This is the artefact an on-call engineer reads at 03:00.  It names every rule that was
    considered, not only the ones that fired, because "why did nothing stop this?" is the harder
    question.
    """

    lines = [
        f"hook {outcome.hook_point} against policy snapshot {outcome.policy_snapshot_hash}",
    ]
    for item in outcome.trace:
        verdict = "MATCHED" if item.matched else "skipped"
        obligations = f" obligations={list(item.obligations)}" if item.obligations else ""
        lines.append(
            f"  [{verdict}] {item.rule_id} -> {item.decision}{obligations}: "
            f"{item.explanation} ({item.detail})"
        )
    lines.append(
        f"decision {outcome.decision} with obligations {list(outcome.obligations)}"
    )
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """A pending human or second-party decision, with an expiry.

    Approvals expire because a decision taken against last week's subject is not a decision about
    this one.  Consuming an expired approval raises ``APPROVAL_EXPIRED`` rather than being treated
    as a grant.
    """

    approval_id: str
    hook_point: str
    decision: Decision
    policy_snapshot_hash: str
    subject_digest: str
    requested_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.approval_id, "approval_id")
        if self.decision not in APPROVAL_DECISIONS:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"{self.decision} does not require an approval",
                recommended_action="only build approval requests for ASK/ESCALATE/REVIEW",
            )
        if self.expires_at <= self.requested_at:
            raise KernelError(
                code="MALFORMED_INPUT",
                message="approval expires_at must be strictly after requested_at",
                recommended_action="grant a positive approval window",
            )

    def assert_valid(self, now: datetime, *, subject_digest: str,
                     policy_snapshot_hash: str) -> None:
        """Raise unless the approval is live and still about the same subject and policy."""

        if now >= self.expires_at:
            raise KernelError(
                code="APPROVAL_EXPIRED",
                message=(
                    f"approval {self.approval_id!r} expired at "
                    f"{format_timestamp(self.expires_at)}"
                ),
                retryable=False,
                recommended_action="request approval again against the current snapshot",
            )
        if subject_digest != self.subject_digest:
            raise KernelError(
                code="APPROVAL_REQUIRED",
                message=f"approval {self.approval_id!r} was granted for a different subject",
                recommended_action="request approval for this subject",
            )
        if policy_snapshot_hash != self.policy_snapshot_hash:
            raise KernelError(
                code="STALE_POLICY_SNAPSHOT",
                message=f"approval {self.approval_id!r} was granted under a different policy",
                recommended_action="re-evaluate and request approval again",
            )

    def to_payload(self) -> dict[str, Any]:
        core = {
            "approvalId": self.approval_id,
            "hookPoint": self.hook_point,
            "decision": str(self.decision),
            "policySnapshotHash": self.policy_snapshot_hash,
            "subjectDigest": self.subject_digest,
            "requestedAt": format_timestamp(self.requested_at),
            "expiresAt": format_timestamp(self.expires_at),
        }
        return {**core, "digest": digest(core)}


def approval_for(outcome: PolicyOutcome, *, now: datetime, ttl_seconds: int) -> ApprovalRequest:
    """Build the approval this outcome demands.

    The id is derived from the outcome's own digest, so a duplicate delivery of the same hook
    event produces the same approval id instead of a second pending request.
    """

    require_int(ttl_seconds, "ttl_seconds", minimum=1, maximum=2_592_000)
    fingerprint = digest({
        "hookPoint": outcome.hook_point,
        "decision": str(outcome.decision),
        "policySnapshotHash": outcome.policy_snapshot_hash,
        "subjectDigest": outcome.subject_digest,
    })
    return ApprovalRequest(
        approval_id="apr-" + fingerprint.split(":", 1)[1][:32],
        hook_point=outcome.hook_point,
        decision=outcome.decision,
        policy_snapshot_hash=outcome.policy_snapshot_hash,
        subject_digest=outcome.subject_digest,
        requested_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


def snapshot_from_layers(snapshot_id: str, layers: Sequence[Mapping[str, Any]]) -> PolicySnapshot:
    """Flatten ordered policy layers (platform first, run-local last) into one snapshot.

    Layers are concatenated, not merged: a later layer can add a rule but never edit or delete an
    earlier one.  Rule ids must be unique across every layer, which makes "which layer denied me"
    answerable from the rule id alone.
    """

    rules: list[PolicyRule] = []
    for index, raw in enumerate(layers):
        layer = require_mapping(raw, f"policy_layers[{index}]")
        reject_unknown_fields(layer, ("layerId", "rules"), field_name=f"policy_layers[{index}]")
        layer_id = require_identifier(layer.get("layerId"), f"policy_layers[{index}].layerId")
        raw_rules = layer.get("rules", ())
        if isinstance(raw_rules, (str, bytes)) or not isinstance(raw_rules, Sequence):
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"policy_layers[{index}].rules must be an array",
                recommended_action="supply rules as a JSON array",
            )
        for position, raw_rule in enumerate(raw_rules):
            rules.append(PolicyRule.from_mapping(
                raw_rule, where=f"policy_layers[{index}]({layer_id}).rules[{position}]"))
    return PolicySnapshot(snapshot_id=snapshot_id, rules=tuple(rules))


@register("policy-hook-kernel")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point: evaluate one hook event against one policy snapshot.

    A DENY is returned as a successful evaluation, not raised: the obligations and the rule trace
    are the deliverable, and an exception would throw them away.  Malformed input, an unknown hook
    point, a stale snapshot and an engine type error all still raise.
    """

    body = require_mapping(request, "request")
    reject_unknown_fields(
        body, ("hook_event", "policy_layers", "run_context", "tool_or_step_context"),
        field_name="request",
    )
    for required in ("hook_event", "policy_layers", "run_context"):
        if required not in body:
            raise KernelError(
                code="MISSING_REQUIRED_INPUT",
                message=f"request.{required} is required",
                recommended_action=f"supply {required}",
            )

    hook_event = require_mapping(body["hook_event"], "hook_event")
    reject_unknown_fields(hook_event, ("hookPoint", "subject"), field_name="hook_event")
    hook_point = require_str(hook_event.get("hookPoint"), "hook_event.hookPoint", max_length=64)
    subject = dict(require_mapping(hook_event.get("subject", {}), "hook_event.subject"))

    step_context = body.get("tool_or_step_context")
    if step_context is not None:
        extra = require_mapping(step_context, "tool_or_step_context")
        overlapping = sorted(set(extra) & set(subject))
        if overlapping:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=(
                    "tool_or_step_context would silently override subject fields "
                    f"{overlapping}"
                ),
                recommended_action="state each subject field exactly once",
                details={"overlapping": overlapping},
            )
        subject.update(extra)

    run_context = require_mapping(body["run_context"], "run_context")
    reject_unknown_fields(
        run_context, ("policySnapshotHash", "snapshotId", "now", "approvalTtlSeconds"),
        field_name="run_context",
    )
    declared_hash = require_str(run_context.get("policySnapshotHash"),
                                "run_context.policySnapshotHash")
    snapshot_id = require_identifier(run_context.get("snapshotId", "policy-snapshot"),
                                     "run_context.snapshotId")
    now = parse_timestamp(run_context.get("now"), "run_context.now")
    approval_ttl = require_int(run_context.get("approvalTtlSeconds", 3600),
                               "run_context.approvalTtlSeconds", minimum=1, maximum=2_592_000)

    layers = body["policy_layers"]
    if isinstance(layers, Mapping):
        layers = require_mapping(layers, "policy_layers").get("layers", ())
    if isinstance(layers, (str, bytes)) or not isinstance(layers, Sequence):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="policy_layers must be an array of layers or {layers: [...]}",
            recommended_action="supply ordered policy layers",
        )
    snapshot = snapshot_from_layers(snapshot_id, layers)
    outcome = snapshot.evaluate(hook_point, subject, declared_snapshot_hash=declared_hash)

    modified_input: Mapping[str, Any] | None = None
    if outcome.decision is Decision.MODIFY_INPUT:
        modified_input = {
            "required": True,
            "obligations": list(outcome.obligations),
            "subjectDigest": outcome.subject_digest,
        }
    approval: Mapping[str, Any] | None = None
    if outcome.requires_approval:
        approval = approval_for(outcome, now=now, ttl_seconds=approval_ttl).to_payload()

    evidence_core = {
        "policySnapshotHash": snapshot.snapshot_hash,
        "snapshotId": snapshot.snapshot_id,
        "ruleCount": len(snapshot.rules),
        "explanation": list(explain(outcome)),
    }
    audit_core = {
        "type": "policy.decision",
        "hookPoint": outcome.hook_point,
        "decision": str(outcome.decision),
        "obligations": list(outcome.obligations),
        "matchedRuleIds": list(outcome.matched_rule_ids),
        "policySnapshotHash": snapshot.snapshot_hash,
        "subjectDigest": outcome.subject_digest,
        "recordedAt": format_timestamp(now),
    }
    return {
        "policy_decision": outcome.to_payload(),
        "modified_input": modified_input,
        "approval_request": approval,
        "policy_evidence": {**evidence_core, "digest": digest(evidence_core)},
        "audit_event": {**audit_core, "digest": digest(audit_core),
                        "idempotencyKey": digest(audit_core)},
    }
