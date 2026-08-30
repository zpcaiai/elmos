"""K5 independent assurance plane.

Review evidence is accepted only when scope, credential and producer
independence are explicit.  Watchdog/advisor execution is an external effect
and therefore remains ``NOT_RUN`` until an adapter returns separately verified
evidence.  Unknown evidence and reviewer disagreement fail closed.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Callable, Mapping, Sequence, TypeVar

from .canonical import digest_object, require_sha256_digest
from .contracts import EvidenceRecord, EvidenceStatus, ExecutionContext, ResourceScope
from .errors import AuthorizationError, ConflictError, UnknownCapabilityError, ValidationError
from .registry import CAPABILITY_REGISTRY, OperationSpec


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} is required", code="INVALID_INPUT")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware", code="INVALID_TIME")
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


class FindingSeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class FindingRoute(StrEnum):
    BLOCKER = "BLOCKER"
    CONCERN = "CONCERN"
    NIT = "NIT"


class AdvisorStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"
    QUARANTINED = "QUARANTINED"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"


class WatchdogKind(StrEnum):
    ARCHITECTURE = "architecture"
    MIGRATION = "migration"
    SECURITY = "security"
    TRANSACTION = "transaction"
    CONCURRENCY = "concurrency"
    DATABASE = "database"
    API_CONTRACT = "api-contract"
    PERFORMANCE = "performance"
    PROOF = "proof"


class AssuranceEffectKind(StrEnum):
    RUN_ADVISOR = "RUN_ADVISOR"
    RUN_WATCHDOG = "RUN_WATCHDOG"
    OPEN_TOOL_SESSION = "OPEN_TOOL_SESSION"


@dataclass(frozen=True, slots=True)
class ReviewerCredential:
    credential_id: str
    subject_principal_id: str
    issuer_principal_id: str
    credential_digest: str
    tenant_id: str
    project_id: str
    repository_id: str
    allowed_evidence_types: tuple[str, ...]
    issued_at: datetime
    expires_at: datetime
    independently_verified: bool

    def __post_init__(self) -> None:
        for value, name in (
            (self.credential_id, "credential_id"),
            (self.subject_principal_id, "subject_principal_id"),
            (self.issuer_principal_id, "issuer_principal_id"),
            (self.tenant_id, "tenant_id"),
            (self.project_id, "project_id"),
            (self.repository_id, "repository_id"),
        ):
            _required(value, name)
        require_sha256_digest(self.credential_digest, field="credential_digest")
        _aware(self.issued_at, "issued_at")
        _aware(self.expires_at, "expires_at")
        if self.issued_at >= self.expires_at:
            raise ValidationError("credential validity is empty", code="INVALID_CREDENTIAL")
        if not self.allowed_evidence_types or len(set(self.allowed_evidence_types)) != len(
            self.allowed_evidence_types
        ):
            raise ValidationError(
                "credential evidence types must be non-empty and unique", code="INVALID_CREDENTIAL"
            )


@dataclass(frozen=True, slots=True)
class CredentialVerificationReceipt:
    verification_id: str
    credential_id: str
    credential_digest: str
    subject_principal_id: str
    verifier_principal_id: str
    verifier_independence_domain: str
    scope: ResourceScope
    evidence_digest: str
    verified_at: datetime
    expires_at: datetime
    status: EvidenceStatus = EvidenceStatus.VALID

    def __post_init__(self) -> None:
        for value, name in (
            (self.verification_id, "verification_id"),
            (self.credential_id, "credential_id"),
            (self.subject_principal_id, "subject_principal_id"),
            (self.verifier_principal_id, "verifier_principal_id"),
            (self.verifier_independence_domain, "verifier_independence_domain"),
        ):
            _required(value, name)
        require_sha256_digest(self.credential_digest, field="credential_digest")
        require_sha256_digest(self.evidence_digest, field="evidence_digest")
        _aware(self.verified_at, "verified_at")
        _aware(self.expires_at, "expires_at")
        if self.verified_at >= self.expires_at:
            raise ValidationError("credential verification validity is empty", code="INVALID_CREDENTIAL_RECEIPT")


@dataclass(frozen=True, slots=True)
class ReviewerPrincipal:
    principal_id: str
    independence_domain: str
    roles: tuple[str, ...]
    credential: ReviewerCredential

    def __post_init__(self) -> None:
        _required(self.principal_id, "principal_id")
        _required(self.independence_domain, "independence_domain")
        if self.credential.subject_principal_id != self.principal_id:
            raise AuthorizationError("credential subject mismatch", code="REVIEWER_CREDENTIAL_MISMATCH")
        if not self.roles:
            raise ValidationError("reviewer roles are required", code="INVALID_REVIEWER")


@dataclass(frozen=True, slots=True)
class ReviewEvidencePath:
    path_id: str
    scope: ResourceScope
    executor_principal_id: str
    executor_independence_domain: str
    reviewer: ReviewerPrincipal
    evidence: tuple[EvidenceRecord, ...]
    credential_verification: CredentialVerificationReceipt

    def __post_init__(self) -> None:
        for value, name in (
            (self.path_id, "path_id"),
            (self.executor_principal_id, "executor_principal_id"),
            (self.executor_independence_domain, "executor_independence_domain"),
        ):
            _required(value, name)

    def validate(self, *, now: datetime) -> "ReviewEvidencePath":
        _aware(now, "now")
        credential = self.reviewer.credential
        if self.reviewer.principal_id == self.executor_principal_id:
            raise AuthorizationError("reviewer is the executor", code="REVIEWER_NOT_INDEPENDENT")
        if self.reviewer.independence_domain == self.executor_independence_domain:
            raise AuthorizationError(
                "reviewer shares executor independence domain", code="REVIEWER_NOT_INDEPENDENT"
            )
        if credential.issuer_principal_id in {
            self.executor_principal_id,
            self.reviewer.principal_id,
        }:
            raise AuthorizationError(
                "credential is self-issued or executor-issued", code="REVIEWER_CREDENTIAL_NOT_INDEPENDENT"
            )
        receipt = self.credential_verification
        if receipt.verifier_principal_id in {
            self.executor_principal_id,
            self.reviewer.principal_id,
        }:
            raise AuthorizationError(
                "credential verifier is not independent", code="REVIEWER_CREDENTIAL_NOT_INDEPENDENT"
            )
        if not credential.independently_verified or not (credential.issued_at <= now < credential.expires_at):
            raise AuthorizationError("reviewer credential is not valid", code="REVIEWER_CREDENTIAL_INVALID")
        if (
            receipt.status is not EvidenceStatus.VALID
            or not (receipt.verified_at <= now < receipt.expires_at)
            or receipt.credential_id != credential.credential_id
            or receipt.credential_digest != credential.credential_digest
            or receipt.subject_principal_id != self.reviewer.principal_id
            or not _same_scope(receipt.scope, self.scope)
            or receipt.verifier_independence_domain
            in {self.executor_independence_domain, self.reviewer.independence_domain}
        ):
            raise AuthorizationError(
                "credential verification receipt is invalid or not independent",
                code="REVIEWER_CREDENTIAL_NOT_INDEPENDENT",
            )
        if (
            credential.tenant_id,
            credential.project_id,
            credential.repository_id,
        ) != (self.scope.tenant_id, self.scope.project_id, self.scope.repository_id):
            raise AuthorizationError("reviewer credential scope mismatch", code="REVIEWER_SCOPE_MISMATCH")
        if not self.evidence:
            raise ValidationError("review evidence path is empty", code="MISSING_REVIEW_EVIDENCE")
        allowed = set(credential.allowed_evidence_types)
        for record in self.evidence:
            if record.scope is None or not _same_scope(record.scope, self.scope):
                raise AuthorizationError("review evidence scope mismatch", code="EVIDENCE_SCOPE_MISMATCH")
            if record.producer == self.executor_principal_id:
                raise AuthorizationError("executor self-evidence is not independent", code="EVIDENCE_NOT_INDEPENDENT")
            if record.evidence_type not in allowed:
                raise AuthorizationError("review evidence type is not granted", code="EVIDENCE_TYPE_DENIED")
            if record.status is not EvidenceStatus.VALID:
                raise ValidationError(
                    "unknown, stale or invalid evidence cannot close review",
                    code="UNKNOWN_REVIEW_EVIDENCE",
                    details={"evidence_id": record.evidence_id, "status": record.status.value},
                )
        return self


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    scope: ResourceScope
    reviewer_principal_id: str
    severity: FindingSeverity
    confidence: Decimal
    artifact: str
    symbol: str
    source_range: str
    violated_invariant: str
    evidence_ids: tuple[str, ...]
    reasoning_path: str
    certification_impact: str
    recommended_remediation: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.finding_id, "finding_id"),
            (self.reviewer_principal_id, "reviewer_principal_id"),
            (self.artifact, "artifact"),
            (self.symbol, "symbol"),
            (self.source_range, "source_range"),
            (self.violated_invariant, "violated_invariant"),
            (self.reasoning_path, "reasoning_path"),
            (self.certification_impact, "certification_impact"),
            (self.recommended_remediation, "recommended_remediation"),
        ):
            _required(value, name)
        if not isinstance(self.confidence, Decimal) or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValidationError("finding confidence must be Decimal in [0,1]", code="INVALID_FINDING")
        if not self.evidence_ids or len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValidationError("material finding requires unique evidence ids", code="INVALID_FINDING")

    @property
    def route(self) -> FindingRoute:
        if self.severity in {FindingSeverity.P0, FindingSeverity.P1}:
            return FindingRoute.BLOCKER
        if self.severity is FindingSeverity.P2:
            return FindingRoute.CONCERN
        return FindingRoute.NIT

    def fingerprint(self) -> str:
        return digest_object(
            {
                "scope": self.scope,
                "severity": self.severity,
                "artifact": self.artifact,
                "symbol": self.symbol,
                "source_range": self.source_range,
                "invariant": self.violated_invariant,
            },
            domain="assurance-finding",
        )


class FindingDeduplicator:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str, str, str]] = set()

    def accept(self, finding: Finding) -> bool:
        key = (
            finding.scope.tenant_id,
            finding.scope.project_id,
            finding.scope.repository_id,
            finding.fingerprint(),
        )
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


class AdvisorRateLimiter:
    def __init__(self, limit: int, window: timedelta) -> None:
        if limit < 1 or window <= timedelta(0):
            raise ValidationError("rate limit must be positive", code="INVALID_RATE_LIMIT")
        self.limit = limit
        self.window = window
        self._events: defaultdict[tuple[str, str, str, str], deque[datetime]] = defaultdict(deque)

    def require_capacity(self, scope: ResourceScope, reviewer_id: str, *, now: datetime) -> None:
        _aware(now, "now")
        key = (scope.tenant_id, scope.project_id, scope.repository_id, reviewer_id)
        events = self._events[key]
        cutoff = now - self.window
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            raise ConflictError("advisor rate limit exceeded", code="ADVISOR_RATE_LIMITED")
        events.append(now)


@dataclass(frozen=True, slots=True)
class QuarantinedAdvisorOutput:
    quarantine_id: str
    scope: ResourceScope | None
    reviewer_id: str | None
    reason_code: str
    observed_type: str
    quarantined_at: datetime


class AdvisorBacklog:
    """Bounded queue with isolation and explicit quarantine."""

    def __init__(self, maximum: int, *, deduplicator: FindingDeduplicator | None = None) -> None:
        if maximum < 1:
            raise ValidationError("backlog maximum must be positive", code="INVALID_BACKLOG")
        self.maximum = maximum
        self._deduplicator = deduplicator or FindingDeduplicator()
        self._items: deque[Finding] = deque()
        self._quarantine: list[QuarantinedAdvisorOutput] = []

    @property
    def quarantined(self) -> tuple[QuarantinedAdvisorOutput, ...]:
        return tuple(self._quarantine)

    def ingest(
        self,
        output: object,
        *,
        expected_scope: ResourceScope,
        reviewer_id: str,
        evidence_path: ReviewEvidencePath,
        now: datetime,
    ) -> bool:
        reason: str | None = None
        try:
            evidence_path.validate(now=now)
        except (AuthorizationError, ValidationError):
            reason = "INVALID_EVIDENCE_PATH"
        if reason is None:
            if not isinstance(output, Finding):
                reason = "UNTYPED_ADVISOR_OUTPUT"
            elif not _same_scope(output.scope, expected_scope):
                reason = "ADVISOR_SCOPE_MISMATCH"
            elif output.reviewer_principal_id != reviewer_id:
                reason = "ADVISOR_PRINCIPAL_MISMATCH"
            elif not set(output.evidence_ids).issubset(
                {item.evidence_id for item in evidence_path.evidence}
            ):
                reason = "ADVISOR_EVIDENCE_MISMATCH"
        if reason is not None:
            quarantine_id = digest_object(
                {
                    "reason": reason,
                    "reviewer": reviewer_id,
                    "type": type(output).__name__,
                    "at": now,
                },
                domain="advisor-quarantine",
            )
            self._quarantine.append(
                QuarantinedAdvisorOutput(
                    quarantine_id,
                    getattr(output, "scope", None),
                    reviewer_id,
                    reason,
                    type(output).__name__,
                    now,
                )
            )
            return False
        assert isinstance(output, Finding)
        if not self._deduplicator.accept(output):
            return False
        if len(self._items) >= self.maximum:
            raise ConflictError("advisor backlog is full", code="ADVISOR_BACKPRESSURE")
        self._items.append(output)
        return True

    def drain(self, maximum: int | None = None) -> tuple[Finding, ...]:
        count = len(self._items) if maximum is None else min(maximum, len(self._items))
        return tuple(self._items.popleft() for _ in range(count))


@dataclass(frozen=True, slots=True)
class AdvisorToolGrant:
    grant_id: str
    scope: ResourceScope
    reviewer_id: str
    tools: tuple[str, ...]
    operations: tuple[str, ...]
    expires_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.grant_id, "grant_id"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _required(value, name)
        _aware(self.expires_at, "expires_at")
        if not self.tools or not self.operations:
            raise ValidationError("advisor tool grant selectors are required", code="INVALID_ADVISOR_GRANT")
        if len(set(self.tools)) != len(self.tools) or len(set(self.operations)) != len(self.operations):
            raise ValidationError("advisor tool grant selectors must be unique", code="INVALID_ADVISOR_GRANT")

    def require(self, *, scope: ResourceScope, reviewer_id: str, tool: str, operation: str, now: datetime) -> None:
        if not _same_scope(self.scope, scope) or self.reviewer_id != reviewer_id:
            raise AuthorizationError("advisor tool grant scope mismatch", code="ADVISOR_TOOL_DENIED")
        if now >= self.expires_at or tool not in self.tools or operation not in self.operations:
            raise AuthorizationError("advisor tool is not granted", code="ADVISOR_TOOL_DENIED")


@dataclass(frozen=True, slots=True)
class AssuranceEffectRequest:
    request_id: str
    context: ExecutionContext
    kind: AssuranceEffectKind
    reviewer_id: str
    watchdog: WatchdogKind | None
    input_evidence_ids: tuple[str, ...]
    status: AdvisorStatus = AdvisorStatus.NOT_RUN
    external_evidence_status: AdvisorStatus = AdvisorStatus.NOT_RUN

    def __post_init__(self) -> None:
        if self.status is not AdvisorStatus.NOT_RUN or self.external_evidence_status is not AdvisorStatus.NOT_RUN:
            raise ValidationError(
                "external assurance effects must originate NOT_RUN", code="FABRICATED_ASSURANCE_EFFECT"
            )


class IndependentAdvisorRuntime:
    def request(
        self,
        context: ExecutionContext,
        *,
        reviewer: ReviewerPrincipal,
        evidence_ids: Sequence[str],
        now: datetime,
        watchdog: WatchdogKind | None = None,
    ) -> AssuranceEffectRequest:
        credential = reviewer.credential
        if not credential.independently_verified or not (
            credential.issued_at <= now < credential.expires_at
        ):
            raise AuthorizationError("reviewer credential is expired", code="REVIEWER_CREDENTIAL_INVALID")
        if (
            credential.tenant_id,
            credential.project_id,
            credential.repository_id,
        ) != (
            context.scope.tenant_id,
            context.scope.project_id,
            context.scope.repository_id,
        ):
            raise AuthorizationError("reviewer scope mismatch", code="REVIEWER_SCOPE_MISMATCH")
        kind = AssuranceEffectKind.RUN_ADVISOR if watchdog is None else AssuranceEffectKind.RUN_WATCHDOG
        request_id = digest_object(
            {
                "idempotency_key": context.idempotency_key,
                "context": context,
                "reviewer": reviewer.principal_id,
                "watchdog": watchdog,
                "evidence": tuple(evidence_ids),
            },
            domain="assurance-effect",
        )
        return AssuranceEffectRequest(
            request_id,
            context,
            kind,
            reviewer.principal_id,
            watchdog,
            tuple(evidence_ids),
        )


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class IsolatedAdvisorResult:
    status: AdvisorStatus
    value: object | None
    failure_type: str | None


class AdvisorFailureIsolation:
    @staticmethod
    def run(call: Callable[[], T]) -> IsolatedAdvisorResult:
        try:
            return IsolatedAdvisorResult(AdvisorStatus.PASS, call(), None)
        except Exception as exc:  # isolate an untrusted/external advisor boundary
            return IsolatedAdvisorResult(AdvisorStatus.INCONCLUSIVE, None, type(exc).__name__)


class ReviewerVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_RUN = "NOT_RUN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ReviewVote:
    reviewer_id: str
    independence_domain: str
    verdict: ReviewerVerdict
    evidence_path_id: str
    finding_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for value, name in (
            (self.reviewer_id, "reviewer_id"),
            (self.independence_domain, "independence_domain"),
            (self.evidence_path_id, "evidence_path_id"),
        ):
            _required(value, name)
        if len(set(self.finding_ids)) != len(self.finding_ids):
            raise ValidationError("vote finding ids must be unique", code="INVALID_REVIEW_VOTE")


@dataclass(frozen=True, slots=True)
class ConsensusDecision:
    verdict: ReviewerVerdict
    reviewer_ids: tuple[str, ...]
    disagreement: bool
    certification_allowed: bool
    reason: str


class ReviewerConsensus:
    def __init__(self, minimum_independent_reviewers: int = 2) -> None:
        if minimum_independent_reviewers < 1:
            raise ValidationError("reviewer minimum must be positive", code="INVALID_CONSENSUS")
        self.minimum = minimum_independent_reviewers

    def decide(self, votes: Sequence[ReviewVote]) -> ConsensusDecision:
        reviewer_ids = tuple(vote.reviewer_id for vote in votes)
        if len(set(reviewer_ids)) != len(reviewer_ids):
            raise ConflictError("duplicate reviewer vote", code="DUPLICATE_REVIEWER_VOTE")
        domains = {vote.independence_domain for vote in votes}
        if len(votes) < self.minimum or len(domains) < self.minimum:
            return ConsensusDecision(
                ReviewerVerdict.INCONCLUSIVE,
                reviewer_ids,
                False,
                False,
                "insufficient independent reviewers",
            )
        verdicts = {vote.verdict for vote in votes}
        non_closing = {
            ReviewerVerdict.BLOCKED,
            ReviewerVerdict.INCONCLUSIVE,
            ReviewerVerdict.NOT_RUN,
            ReviewerVerdict.UNKNOWN,
        }
        if verdicts.intersection(non_closing):
            return ConsensusDecision(
                ReviewerVerdict.BLOCKED,
                reviewer_ids,
                len(verdicts) > 1,
                False,
                "a reviewer result is non-closing",
            )
        if ReviewerVerdict.FAIL in verdicts and ReviewerVerdict.PASS in verdicts:
            return ConsensusDecision(
                ReviewerVerdict.INCONCLUSIVE,
                reviewer_ids,
                True,
                False,
                "reviewer disagreement requires explicit resolution",
            )
        verdict = ReviewerVerdict.FAIL if ReviewerVerdict.FAIL in verdicts else ReviewerVerdict.PASS
        return ConsensusDecision(
            verdict,
            reviewer_ids,
            False,
            verdict is ReviewerVerdict.PASS,
            "independent reviewers agree",
        )


@dataclass(frozen=True, slots=True)
class ReleaseReviewDecision:
    verdict: ReviewerVerdict
    blocking_finding_ids: tuple[str, ...]
    evidence_path_ids: tuple[str, ...]
    certification_allowed: bool
    reason: str


class ReleaseVerdictReviewer:
    def __init__(self, consensus: ReviewerConsensus | None = None) -> None:
        self._consensus = consensus or ReviewerConsensus()

    def evaluate(
        self,
        *,
        paths: Sequence[ReviewEvidencePath],
        votes: Sequence[ReviewVote],
        findings: Sequence[Finding],
        now: datetime,
    ) -> ReleaseReviewDecision:
        for path in paths:
            path.validate(now=now)
        if paths and any(not _same_scope(path.scope, paths[0].scope) for path in paths[1:]):
            raise AuthorizationError("assurance paths cross resource scopes", code="REVIEW_PATH_SCOPE_MISMATCH")
        paths_by_id = {path.path_id: path for path in paths}
        for vote in votes:
            vote_path = paths_by_id.get(vote.evidence_path_id)
            if (
                vote_path is None
                or vote.reviewer_id != vote_path.reviewer.principal_id
                or vote.independence_domain != vote_path.reviewer.independence_domain
            ):
                raise AuthorizationError("vote evidence path is missing or mismatched", code="VOTE_EVIDENCE_PATH_MISSING")
        path_ids = set(paths_by_id)
        evidence_ids = {
            record.evidence_id for path in paths for record in path.evidence
        }
        reviewer_ids = {path.reviewer.principal_id for path in paths}
        if findings and not paths:
            raise AuthorizationError("findings require assurance paths", code="FINDING_PATH_MISMATCH")
        for finding in findings:
            if (
                not _same_scope(finding.scope, paths[0].scope)
                or finding.reviewer_principal_id not in reviewer_ids
                or not set(finding.evidence_ids).issubset(evidence_ids)
            ):
                raise AuthorizationError("finding assurance path mismatch", code="FINDING_PATH_MISMATCH")
        blocking = tuple(
            finding.finding_id
            for finding in findings
            if finding.severity in {FindingSeverity.P0, FindingSeverity.P1}
        )
        consensus = self._consensus.decide(votes)
        if blocking:
            return ReleaseReviewDecision(
                ReviewerVerdict.FAIL,
                blocking,
                tuple(sorted(path_ids)),
                False,
                "unresolved P0/P1 findings",
            )
        return ReleaseReviewDecision(
            consensus.verdict,
            (),
            tuple(sorted(path_ids)),
            consensus.certification_allowed,
            consensus.reason,
        )


@dataclass(frozen=True, slots=True)
class CapabilityBinding:
    capability: str
    source_owner: str
    canonical_owner: str
    handler: str
    input_contract: str
    output_contract: str
    external_effect: bool = False


_K5_BINDING_ROWS = (
    ("independent-advisor-runtime", "K5", "K5", "IndependentAdvisorRuntime.request", "review request", "AssuranceEffectRequest", True),
    ("advisor-context-delta", "K5", "K5", "ReviewEvidencePath", "evidence delta", "ReviewEvidencePath", False),
    ("advisor-private-context", "K5", "K5", "ReviewerPrincipal", "private context ref", "authorization", False),
    ("advisor-tool-session", "K5", "K5", "IndependentAdvisorRuntime.request", "AdvisorToolGrant", "AssuranceEffectRequest", True),
    ("advisor-tool-grant-policy", "K5", "K5", "AdvisorToolGrant.require", "tool request", "authorization", False),
    ("advisor-severity-router", "K5", "K5", "Finding.route", "Finding", "FindingRoute", False),
    ("advisor-nit", "K5", "K5", "Finding[P3]", "Finding", "NIT", False),
    ("advisor-concern", "K5", "K5", "Finding[P2]", "Finding", "CONCERN", False),
    ("advisor-blocker", "K5", "K5", "Finding[P0/P1]", "Finding", "BLOCKER", False),
    ("advisor-dedup", "K5", "K5", "FindingDeduplicator.accept", "Finding", "bool", False),
    ("advisor-rate-limit", "K5", "K5", "AdvisorRateLimiter.require_capacity", "reviewer event", "authorization", False),
    ("advisor-backlog", "K5", "K5", "AdvisorBacklog.ingest/drain", "Finding", "Finding[]", False),
    ("advisor-backpressure", "K5", "K5", "AdvisorBacklog.ingest", "Finding", "bounded queue result", False),
    ("advisor-quarantine", "K5", "K5", "AdvisorBacklog.ingest", "advisor output", "QuarantinedAdvisorOutput", False),
    ("advisor-failure-isolation", "K5", "K5", "AdvisorFailureIsolation.run", "advisor call", "IsolatedAdvisorResult", False),
    ("architecture-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[architecture]", "evidence ids", "AssuranceEffectRequest", True),
    ("migration-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[migration]", "evidence ids", "AssuranceEffectRequest", True),
    ("security-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[security]", "evidence ids", "AssuranceEffectRequest", True),
    ("transaction-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[transaction]", "evidence ids", "AssuranceEffectRequest", True),
    ("concurrency-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[concurrency]", "evidence ids", "AssuranceEffectRequest", True),
    ("database-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[database]", "evidence ids", "AssuranceEffectRequest", True),
    ("api-contract-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[api-contract]", "evidence ids", "AssuranceEffectRequest", True),
    ("performance-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[performance]", "evidence ids", "AssuranceEffectRequest", True),
    ("proof-watchdog", "K5", "K5", "IndependentAdvisorRuntime.request[proof]", "evidence ids", "AssuranceEffectRequest", True),
    ("reviewer-consensus", "K5", "K5", "ReviewerConsensus.decide", "ReviewVote[]", "ConsensusDecision", False),
    ("reviewer-disagreement-resolver", "K5", "K5", "ReviewerConsensus.decide", "ReviewVote[]", "INCONCLUSIVE", False),
    ("evidence-first-review", "K5", "K5", "ReviewEvidencePath.validate", "EvidenceRecord[]", "ReviewEvidencePath", False),
    ("release-verdict-reviewer", "K5", "K5", "ReleaseVerdictReviewer.evaluate", "paths+votes+findings", "ReleaseReviewDecision", False),
)

K5_CAPABILITIES = tuple(row[0] for row in _K5_BINDING_ROWS)
K5_OPERATION_BINDINGS: Mapping[str, CapabilityBinding] = MappingProxyType(
    {row[0]: CapabilityBinding(*row) for row in _K5_BINDING_ROWS}
)
K5_OPERATION_SPECS: Mapping[str, OperationSpec] = MappingProxyType(
    {name: CAPABILITY_REGISTRY[name] for name in K5_CAPABILITIES}
)


def resolve_k5_binding(capability: str) -> CapabilityBinding:
    try:
        return K5_OPERATION_BINDINGS[capability]
    except KeyError as exc:
        raise UnknownCapabilityError(
            "unknown K5 capability; generic fallback is forbidden",
            code="UNKNOWN_K5_CAPABILITY",
            details={"capability": capability},
        ) from exc


if len(K5_CAPABILITIES) != 28 or len(set(K5_CAPABILITIES)) != len(K5_CAPABILITIES):
    raise RuntimeError("K5 capability bindings must contain exactly 28 unique operations")
