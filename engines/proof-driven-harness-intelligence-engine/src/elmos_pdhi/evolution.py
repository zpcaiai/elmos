"""K7 governed failure-to-skill evolution lifecycle.

One repair can become a lesson or an experimental candidate.  It can never
become a production Skill without independent corpus evidence, exact versioned
contracts and an externally authorized promotion decision.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Mapping, Protocol, Sequence
import threading

from .canonical import digest_object, require_sha256_digest, utc_now
from .contracts import SkillLifecycleStatus, SkillManifest
from .errors import AuthorizationError, ValidationError


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    memory_type: str
    tenant_id: str
    project_id: str
    source_revision: str
    payload: Mapping[str, Any]
    evidence_ids: tuple[str, ...]
    created_at: datetime
    digest: str


@dataclass(frozen=True, slots=True)
class FixtureRecord:
    fixture_id: str
    kind: str
    input_digest: str
    expected_digest: str
    independent: bool
    evidence_id: str
    verification_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"positive", "negative", "mutation", "holdout", "golden-route"}:
            raise ValidationError("unsupported fixture kind")
        for name in ("input_digest", "expected_digest"):
            require_sha256_digest(getattr(self, name), field=name)
        if self.verification_receipt_digest is not None:
            require_sha256_digest(self.verification_receipt_digest, field="verification_receipt_digest")


@dataclass(frozen=True, slots=True)
class BenchmarkEvidence:
    benchmark_id: str
    corpus_digest: str
    candidate_digest: str
    pass_rate: Decimal
    neighboring_regression_rate: Decimal
    independent: bool
    verifier_id: str
    producer_id: str
    evidence_id: str
    verification_receipt_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.corpus_digest, field="corpus_digest")
        require_sha256_digest(self.candidate_digest, field="candidate_digest")
        for name in ("pass_rate", "neighboring_regression_rate"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value > 1:
                raise ValidationError(f"{name} must be Decimal in [0,1]")
        if self.independent and self.verifier_id == self.producer_id:
            raise ValidationError("independent benchmark requires a distinct verifier")
        if self.verification_receipt_digest is not None:
            require_sha256_digest(self.verification_receipt_digest, field="verification_receipt_digest")


@dataclass(frozen=True, slots=True)
class ExternalCertificationReceipt:
    receipt_id: str
    candidate_digest: str
    evidence_digest: str
    verifier_id: str
    producer_id: str
    authorization_id: str
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for name in ("receipt_id", "verifier_id", "producer_id", "authorization_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValidationError(f"{name} is required")
        if self.verifier_id == self.producer_id:
            raise ValidationError("certification verifier must be independent")
        require_sha256_digest(self.candidate_digest, field="candidate_digest")
        require_sha256_digest(self.evidence_digest, field="evidence_digest")
        if self.issued_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValidationError("certification receipt times must be timezone-aware")
        if self.expires_at <= self.issued_at:
            raise ValidationError("certification receipt validity is empty")


class SkillEvolutionAuthority(Protocol):
    """Trusted base-harness adapter; no default local implementation exists."""

    def verify_fixture(self, fixture: FixtureRecord, candidate: "SkillCandidate") -> bool: ...
    def verify_benchmark(self, evidence: BenchmarkEvidence, candidate: "SkillCandidate") -> bool: ...
    def verify_certification(self, receipt: ExternalCertificationReceipt, candidate: "SkillCandidate") -> bool: ...
    def authorize_production(self, candidate: "SkillCandidate", version: str, authorization_id: str) -> bool: ...
    def authorize_rollback(self, candidate: "SkillCandidate", version: str, authorization_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    candidate_id: str
    tenant_id: str
    project_id: str
    manifest: SkillManifest
    source_memory_ids: tuple[str, ...]
    fixtures: tuple[FixtureRecord, ...]
    benchmarks: tuple[BenchmarkEvidence, ...]
    corpus_digest: str | None
    state: SkillLifecycleStatus
    version: int
    lineage: tuple[str, ...]
    created_at: datetime
    updated_at: datetime
    external_certification_id: str | None = None
    external_certification_digest: str | None = None
    production_version: str | None = None

    def content_digest(self) -> str:
        return digest_object(self, domain="pdhi-skill-candidate")


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    candidate_id: str
    from_state: SkillLifecycleStatus
    to_state: SkillLifecycleStatus
    allowed: bool
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    readiness: str
    decision_digest: str


class EvolutionRepository(Protocol):
    def put_memory(self, record: MemoryRecord) -> None: ...
    def get_memory(self, memory_id: str, tenant_id: str, project_id: str) -> MemoryRecord: ...
    def put_candidate(self, candidate: SkillCandidate, *, expected_version: int | None) -> None: ...
    def get_candidate(self, candidate_id: str, tenant_id: str, project_id: str) -> SkillCandidate: ...
    def candidates(self, tenant_id: str, project_id: str) -> tuple[SkillCandidate, ...]: ...


class LocalEvolutionRepository:
    """Thread-safe local engineering repository; not a production authority."""

    def __init__(self) -> None:
        self._memories: dict[tuple[str, str, str], MemoryRecord] = {}
        self._candidates: dict[tuple[str, str, str], SkillCandidate] = {}
        self._lock = threading.RLock()

    def put_memory(self, record: MemoryRecord) -> None:
        key = (record.tenant_id, record.project_id, record.memory_id)
        with self._lock:
            if key in self._memories and self._memories[key].digest != record.digest:
                raise ValidationError("memory id collision")
            self._memories[key] = record

    def get_memory(self, memory_id: str, tenant_id: str, project_id: str) -> MemoryRecord:
        with self._lock:
            try:
                return self._memories[(tenant_id, project_id, memory_id)]
            except KeyError as exc:
                raise AuthorizationError("memory is unavailable in authenticated scope") from exc

    def put_candidate(self, candidate: SkillCandidate, *, expected_version: int | None) -> None:
        key = (candidate.tenant_id, candidate.project_id, candidate.candidate_id)
        with self._lock:
            current = self._candidates.get(key)
            if expected_version is None:
                if current is not None:
                    raise ValidationError("candidate already exists")
            elif current is None or current.version != expected_version:
                raise ValidationError("candidate version is stale")
            self._candidates[key] = candidate

    def get_candidate(self, candidate_id: str, tenant_id: str, project_id: str) -> SkillCandidate:
        with self._lock:
            try:
                return self._candidates[(tenant_id, project_id, candidate_id)]
            except KeyError as exc:
                raise AuthorizationError("candidate is unavailable in authenticated scope") from exc

    def candidates(self, tenant_id: str, project_id: str) -> tuple[SkillCandidate, ...]:
        with self._lock:
            return tuple(
                sorted(
                    (item for (tenant, project, _), item in self._candidates.items() if tenant == tenant_id and project == project_id),
                    key=lambda item: item.candidate_id,
                )
            )


ALLOWED_TRANSITIONS: Mapping[SkillLifecycleStatus, frozenset[SkillLifecycleStatus]] = MappingProxyType(
    {
        SkillLifecycleStatus.DRAFT: frozenset({SkillLifecycleStatus.EXPERIMENTAL}),
        SkillLifecycleStatus.EXPERIMENTAL: frozenset({SkillLifecycleStatus.REGRESSION_TESTED, SkillLifecycleStatus.DEPRECATED}),
        SkillLifecycleStatus.REGRESSION_TESTED: frozenset({SkillLifecycleStatus.GOLDEN_ROUTE_TESTED, SkillLifecycleStatus.EXPERIMENTAL, SkillLifecycleStatus.DEPRECATED}),
        SkillLifecycleStatus.GOLDEN_ROUTE_TESTED: frozenset({SkillLifecycleStatus.CERTIFIED, SkillLifecycleStatus.REGRESSION_TESTED, SkillLifecycleStatus.DEPRECATED}),
        SkillLifecycleStatus.CERTIFIED: frozenset({SkillLifecycleStatus.PRODUCTION, SkillLifecycleStatus.DEPRECATED}),
        SkillLifecycleStatus.PRODUCTION: frozenset({SkillLifecycleStatus.DEPRECATED}),
        SkillLifecycleStatus.DEPRECATED: frozenset(),
    }
)


class SkillEvolutionService:
    def __init__(
        self,
        repository: EvolutionRepository,
        authority: SkillEvolutionAuthority | None = None,
    ) -> None:
        self._repository = repository
        self._authority = authority

    def record_memory(
        self,
        *,
        memory_id: str,
        memory_type: str,
        tenant_id: str,
        project_id: str,
        source_revision: str,
        payload: Mapping[str, Any],
        evidence_ids: Sequence[str],
        created_at: datetime | None = None,
    ) -> MemoryRecord:
        if memory_type not in {"project", "repository-semantic", "failure", "counterexample", "repair"}:
            raise ValidationError("unsupported memory type")
        require_sha256_digest(source_revision, field="source_revision")
        evidence = tuple(evidence_ids)
        if not evidence or len(set(evidence)) != len(evidence):
            raise ValidationError("memory requires unique evidence ids")
        timestamp = utc_now() if created_at is None else created_at
        body = {
            "memory_id": memory_id,
            "memory_type": memory_type,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "source_revision": source_revision,
            "payload": payload,
            "evidence_ids": evidence,
            "created_at": timestamp,
        }
        record = MemoryRecord(memory_id, memory_type, tenant_id, project_id, source_revision, MappingProxyType(dict(payload)), evidence, timestamp, digest_object(body, domain="pdhi-memory"))
        self._repository.put_memory(record)
        return record

    def extract_lesson(self, memory: MemoryRecord) -> Mapping[str, Any]:
        if memory.memory_type not in {"failure", "counterexample", "repair"}:
            raise ValidationError("lesson extraction requires failure, counterexample or repair memory")
        trigger = memory.payload.get("trigger")
        invariant = memory.payload.get("invariant")
        remediation = memory.payload.get("remediation")
        if not all(isinstance(item, str) and item.strip() for item in (trigger, invariant, remediation)):
            raise ValidationError("memory lacks bounded trigger/invariant/remediation")
        body = {
            "source_memory_id": memory.memory_id,
            "trigger": trigger,
            "invariant": invariant,
            "remediation": remediation,
            "evidence_ids": memory.evidence_ids,
            "generalization_status": "REQUIRES_INDEPENDENT_CORPUS",
        }
        return MappingProxyType({**body, "lesson_digest": digest_object(body, domain="pdhi-lesson")})

    def create_candidate(
        self,
        *,
        candidate_id: str,
        tenant_id: str,
        project_id: str,
        manifest: SkillManifest,
        source_memory_ids: Sequence[str],
        lineage: Sequence[str] = (),
        now: datetime | None = None,
    ) -> SkillCandidate:
        if manifest.status is not SkillLifecycleStatus.DRAFT:
            raise ValidationError("new candidate manifest must start DRAFT")
        memory_ids = tuple(source_memory_ids)
        if not memory_ids or len(set(memory_ids)) != len(memory_ids):
            raise ValidationError("candidate requires unique source memories")
        for memory_id in memory_ids:
            self._repository.get_memory(memory_id, tenant_id, project_id)
        timestamp = utc_now() if now is None else now
        candidate = SkillCandidate(
            candidate_id,
            tenant_id,
            project_id,
            manifest,
            memory_ids,
            (),
            (),
            None,
            SkillLifecycleStatus.DRAFT,
            1,
            tuple(lineage),
            timestamp,
            timestamp,
        )
        self._repository.put_candidate(candidate, expected_version=None)
        return candidate

    def similarity(self, left: SkillCandidate, right: SkillCandidate) -> Decimal:
        left_terms = set(left.manifest.triggers) | set(left.manifest.acceptance)
        right_terms = set(right.manifest.triggers) | set(right.manifest.acceptance)
        union = left_terms | right_terms
        return Decimal("0") if not union else Decimal(len(left_terms & right_terms)) / Decimal(len(union))

    def conflicts(self, left: SkillCandidate, right: SkillCandidate) -> tuple[str, ...]:
        issues: list[str] = []
        if set(left.manifest.triggers) & set(right.manifest.triggers) and left.manifest.outputs != right.manifest.outputs:
            issues.append("overlapping_triggers_with_incompatible_outputs")
        if left.manifest.name in right.manifest.conflicts or right.manifest.name in left.manifest.conflicts:
            issues.append("explicit_manifest_conflict")
        if left.manifest.name == right.manifest.name and left.manifest.version == right.manifest.version and left.content_digest() != right.content_digest():
            issues.append("same_identity_different_content")
        return tuple(issues)

    def add_fixture(
        self,
        *,
        tenant_id: str,
        project_id: str,
        candidate_id: str,
        expected_version: int,
        fixture: FixtureRecord,
        now: datetime | None = None,
    ) -> SkillCandidate:
        candidate = self._repository.get_candidate(candidate_id, tenant_id, project_id)
        if candidate.version != expected_version:
            raise ValidationError("candidate version is stale")
        if candidate.state in {SkillLifecycleStatus.CERTIFIED, SkillLifecycleStatus.PRODUCTION, SkillLifecycleStatus.DEPRECATED}:
            raise ValidationError("fixtures cannot mutate a sealed candidate")
        if any(item.fixture_id == fixture.fixture_id for item in candidate.fixtures):
            raise ValidationError("fixture id already exists")
        updated = replace(candidate, fixtures=candidate.fixtures + (fixture,), version=candidate.version + 1, updated_at=utc_now() if now is None else now)
        self._repository.put_candidate(updated, expected_version=candidate.version)
        return updated

    def attach_corpus(
        self,
        *,
        tenant_id: str,
        project_id: str,
        candidate_id: str,
        expected_version: int,
        corpus_digest: str,
        now: datetime | None = None,
    ) -> SkillCandidate:
        require_sha256_digest(corpus_digest, field="corpus_digest")
        candidate = self._repository.get_candidate(candidate_id, tenant_id, project_id)
        if candidate.version != expected_version:
            raise ValidationError("candidate version is stale")
        if candidate.state in {SkillLifecycleStatus.CERTIFIED, SkillLifecycleStatus.PRODUCTION, SkillLifecycleStatus.DEPRECATED}:
            raise ValidationError("corpus cannot mutate a sealed candidate")
        updated = replace(candidate, corpus_digest=corpus_digest, version=candidate.version + 1, updated_at=utc_now() if now is None else now)
        self._repository.put_candidate(updated, expected_version=candidate.version)
        return updated

    def record_benchmark(
        self,
        *,
        tenant_id: str,
        project_id: str,
        candidate_id: str,
        expected_version: int,
        evidence: BenchmarkEvidence,
        now: datetime | None = None,
    ) -> SkillCandidate:
        candidate = self._repository.get_candidate(candidate_id, tenant_id, project_id)
        if candidate.version != expected_version:
            raise ValidationError("candidate version is stale")
        if candidate.state in {SkillLifecycleStatus.CERTIFIED, SkillLifecycleStatus.PRODUCTION, SkillLifecycleStatus.DEPRECATED}:
            raise ValidationError("benchmarks cannot mutate a sealed candidate")
        if candidate.corpus_digest is None or evidence.corpus_digest != candidate.corpus_digest:
            raise ValidationError("benchmark corpus does not match candidate corpus")
        if evidence.candidate_digest != candidate.content_digest():
            raise ValidationError("benchmark is stale for current candidate")
        if evidence.independent and (
            evidence.verification_receipt_digest is None
            or self._authority is None
            or not self._authority.verify_benchmark(evidence, candidate)
        ):
            raise AuthorizationError("independent benchmark receipt is not verified")
        updated = replace(candidate, benchmarks=candidate.benchmarks + (evidence,), version=candidate.version + 1, updated_at=utc_now() if now is None else now)
        self._repository.put_candidate(updated, expected_version=candidate.version)
        return updated

    def transition(
        self,
        *,
        tenant_id: str,
        project_id: str,
        candidate_id: str,
        expected_version: int,
        target: SkillLifecycleStatus,
        external_certification_id: str | None = None,
        certification_receipt: ExternalCertificationReceipt | None = None,
        production_version: str | None = None,
        production_authorization_id: str | None = None,
        now: datetime | None = None,
    ) -> PromotionDecision:
        candidate = self._repository.get_candidate(candidate_id, tenant_id, project_id)
        if candidate.version != expected_version:
            raise ValidationError("candidate version is stale")
        if target not in ALLOWED_TRANSITIONS[candidate.state]:
            raise ValidationError(f"invalid skill transition {candidate.state.value}->{target.value}")
        reasons: list[str] = []
        evidence_ids: list[str] = []
        fixture_kinds = {item.kind for item in candidate.fixtures}
        if target is SkillLifecycleStatus.EXPERIMENTAL and not candidate.source_memory_ids:
            reasons.append("source_memory_required")
        if target is SkillLifecycleStatus.REGRESSION_TESTED:
            if not {"positive", "negative"}.issubset(fixture_kinds):
                reasons.append("positive_and_negative_fixtures_required")
            if candidate.corpus_digest is None:
                reasons.append("regression_corpus_required")
        if target is SkillLifecycleStatus.GOLDEN_ROUTE_TESTED:
            required_fixtures = tuple(
                item for item in candidate.fixtures if item.kind in {"golden-route", "holdout"}
            )
            if "golden-route" not in fixture_kinds or "holdout" not in fixture_kinds:
                reasons.append("golden_route_and_holdout_fixtures_required")
            elif any(
                not item.independent
                or item.verification_receipt_digest is None
                or self._authority is None
                or not self._authority.verify_fixture(item, candidate)
                for item in required_fixtures
            ):
                reasons.append("independent_fixture_receipts_required")
            good = [item for item in candidate.benchmarks if item.independent and item.pass_rate == Decimal("1") and item.neighboring_regression_rate == Decimal("0")]
            if not good:
                reasons.append("independent_zero_regression_benchmark_required")
            evidence_ids.extend(item.evidence_id for item in good)
        if target is SkillLifecycleStatus.CERTIFIED:
            if external_certification_id is not None and certification_receipt is None:
                reasons.append("unverified_external_certification_id_rejected")
            if (
                certification_receipt is None
                or certification_receipt.candidate_digest != candidate.content_digest()
                or certification_receipt.expires_at.astimezone(UTC) <= (utc_now() if now is None else now).astimezone(UTC)
                or self._authority is None
                or not self._authority.verify_certification(certification_receipt, candidate)
            ):
                reasons.append("verified_external_certification_receipt_required")
        if target is SkillLifecycleStatus.PRODUCTION:
            if not candidate.external_certification_id or not candidate.external_certification_digest:
                reasons.append("candidate_is_not_externally_certified")
            if not production_version:
                reasons.append("production_version_pin_required")
            if (
                not production_authorization_id
                or not production_version
                or self._authority is None
                or not self._authority.authorize_production(candidate, production_version, production_authorization_id)
            ):
                reasons.append("verified_production_authorization_required")
        allowed = not reasons
        body = {
            "candidate_id": candidate_id,
            "from_state": candidate.state.value,
            "to_state": target.value,
            "allowed": allowed,
            "reasons": reasons,
            "evidence_ids": sorted(set(evidence_ids)),
        }
        decision = PromotionDecision(
            candidate_id,
            candidate.state,
            target,
            allowed,
            tuple(reasons),
            tuple(sorted(set(evidence_ids))),
            "READY_FOR_EXTERNAL_GATE" if target is SkillLifecycleStatus.CERTIFIED and not allowed else ("PROMOTED" if allowed else "BLOCKED"),
            digest_object(body, domain="pdhi-skill-promotion-decision"),
        )
        if allowed:
            updated_manifest = replace(candidate.manifest, status=target)
            updated = replace(
                candidate,
                manifest=updated_manifest,
                state=target,
                version=candidate.version + 1,
                updated_at=utc_now() if now is None else now,
                external_certification_id=(
                    certification_receipt.receipt_id
                    if certification_receipt is not None
                    else candidate.external_certification_id
                ),
                external_certification_digest=(
                    certification_receipt.evidence_digest
                    if certification_receipt is not None
                    else candidate.external_certification_digest
                ),
                production_version=production_version or candidate.production_version,
            )
            self._repository.put_candidate(updated, expected_version=candidate.version)
        return decision

    def rollback_production(
        self,
        *,
        tenant_id: str,
        project_id: str,
        candidate_id: str,
        expected_version: int,
        rollback_to_version: str,
        authorization_id: str,
        now: datetime | None = None,
    ) -> SkillCandidate:
        candidate = self._repository.get_candidate(candidate_id, tenant_id, project_id)
        if candidate.version != expected_version or candidate.state is not SkillLifecycleStatus.PRODUCTION:
            raise ValidationError("only current production candidate can roll back")
        if not rollback_to_version or not authorization_id or rollback_to_version == candidate.production_version:
            raise ValidationError("rollback requires a distinct pinned version and authorization")
        if self._authority is None or not self._authority.authorize_rollback(
            candidate, rollback_to_version, authorization_id
        ):
            raise AuthorizationError("rollback authorization is not independently verified")
        updated = replace(
            candidate,
            state=SkillLifecycleStatus.DEPRECATED,
            manifest=replace(candidate.manifest, status=SkillLifecycleStatus.DEPRECATED, deprecation=f"rolled back by {authorization_id}"),
            version=candidate.version + 1,
            updated_at=utc_now() if now is None else now,
            production_version=rollback_to_version,
        )
        self._repository.put_candidate(updated, expected_version=candidate.version)
        return updated


K7_CAPABILITY_BINDINGS: Mapping[str, str] = MappingProxyType(
    {
        "project-memory": "SkillEvolutionService.record_memory",
        "repository-semantic-memory": "SkillEvolutionService.record_memory",
        "failure-memory": "SkillEvolutionService.record_memory",
        "counterexample-memory": "SkillEvolutionService.record_memory",
        "repair-memory": "SkillEvolutionService.record_memory",
        "lesson-extractor": "SkillEvolutionService.extract_lesson",
        "lesson-generalizer": "SkillEvolutionService.extract_lesson",
        "skill-candidate-generator": "SkillEvolutionService.create_candidate",
        "skill-similarity-dedup": "SkillEvolutionService.similarity",
        "skill-conflict-detector": "SkillEvolutionService.conflicts",
        "skill-fixture-generator": "SkillEvolutionService.add_fixture",
        "skill-negative-fixture-generator": "SkillEvolutionService.add_fixture",
        "mutation-fixture-generator": "SkillEvolutionService.add_fixture",
        "regression-corpus-builder": "SkillEvolutionService.attach_corpus",
        "golden-route-evaluator": "SkillEvolutionService.record_benchmark",
        "skill-benchmark": "SkillEvolutionService.record_benchmark",
        "skill-certifier": "SkillEvolutionService.transition",
        "skill-promoter": "SkillEvolutionService.transition",
        "skill-canary": "SkillEvolutionService.record_benchmark",
        "skill-versioning": "SkillEvolutionService.transition",
        "skill-lineage": "SkillCandidate.lineage",
        "skill-deprecation": "SkillEvolutionService.transition",
        "skill-rollback": "SkillEvolutionService.rollback_production",
    }
)

if len(K7_CAPABILITY_BINDINGS) != 23:
    raise RuntimeError("K7 must bind exactly 23 canonical capabilities")


__all__ = [
    "ALLOWED_TRANSITIONS",
    "BenchmarkEvidence",
    "EvolutionRepository",
    "ExternalCertificationReceipt",
    "FixtureRecord",
    "K7_CAPABILITY_BINDINGS",
    "LocalEvolutionRepository",
    "MemoryRecord",
    "PromotionDecision",
    "SkillCandidate",
    "SkillEvolutionService",
    "SkillEvolutionAuthority",
]
