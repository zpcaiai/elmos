"""Skill 16 — Recipe lifecycle, evaluation and revocation.

A Recipe is a codemod that will be applied to code its author has never seen,
so promoting one is a *safety* decision, not a bookkeeping step.  Four rules
are enforced here rather than left to reviewer discipline:

* **One success promotes nothing.**  :data:`PROMOTION_RULES` states the
  distinct-repository count, precision floor, idempotence requirement,
  adversarial-fixture requirement and signature requirement for each
  transition, and :func:`evaluate_promotion` reports every unmet condition
  instead of the first one.
* **A digest is an identity, not a version label.**  Editing a Recipe changes
  its digest, which makes it a *different* Recipe; :func:`register` refuses
  to rebind an existing digest and :func:`publish_version` requires a new
  version string.
* **Corpus provenance is checked before content.**  A fixture drawn from a
  customer repository needs an explicit sharing grant, and
  :func:`admit_fixture` refuses it otherwise — before the fixture's contents
  are read into an evaluation.
* **Revocation reaches backwards.**  :func:`revoke` records the digest and
  :func:`affected_runs` finds the runs that already applied it, because the
  danger of a bad Recipe is in what it has already done.

Escape defects — a Recipe changing something outside its declared scope — are
weighted separately from ordinary misses: a Recipe that is right 99% of the
time and silently edits an unrelated file 1% of the time is not a 99% Recipe.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .contracts import ContractError, RecipeStatus, RiskClass, sha256_payload
from .recipe import Recipe


class FixtureKind(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    ADVERSARIAL = "adversarial"


class Provenance(StrEnum):
    #: Written for the corpus; no third-party rights attached.
    SYNTHETIC = "synthetic"
    #: Public source under a licence that permits redistribution.
    OPEN_SOURCE = "open-source"
    #: From a customer repository.  Requires an explicit grant.
    CUSTOMER = "customer"


@dataclass(frozen=True, slots=True)
class PromotionRule:
    """What a Recipe must show before it may hold a given status."""

    target: RecipeStatus
    min_distinct_repositories: int
    min_precision: Decimal
    min_recall: Decimal
    max_escape_defects: int
    require_idempotence: bool
    require_adversarial_fixtures: bool
    require_owner_signature: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "target": self.target.value,
            "minDistinctRepositories": self.min_distinct_repositories,
            "minPrecision": str(self.min_precision),
            "minRecall": str(self.min_recall),
            "maxEscapeDefects": self.max_escape_defects,
            "requireIdempotence": self.require_idempotence,
            "requireAdversarialFixtures": self.require_adversarial_fixtures,
            "requireOwnerSignature": self.require_owner_signature,
        }


#: The lifecycle ladder.  Each rung is strictly harder than the one below it.
PROMOTION_RULES: Mapping[RecipeStatus, PromotionRule] = {
    RecipeStatus.QUARANTINED: PromotionRule(
        target=RecipeStatus.QUARANTINED,
        min_distinct_repositories=1,
        min_precision=Decimal("0.80"),
        min_recall=Decimal("0.50"),
        max_escape_defects=0,
        require_idempotence=True,
        require_adversarial_fixtures=False,
        require_owner_signature=False,
    ),
    RecipeStatus.VERIFIED: PromotionRule(
        target=RecipeStatus.VERIFIED,
        min_distinct_repositories=3,
        min_precision=Decimal("0.95"),
        min_recall=Decimal("0.80"),
        max_escape_defects=0,
        require_idempotence=True,
        require_adversarial_fixtures=True,
        require_owner_signature=True,
    ),
    RecipeStatus.CERTIFIED: PromotionRule(
        target=RecipeStatus.CERTIFIED,
        min_distinct_repositories=8,
        min_precision=Decimal("0.99"),
        min_recall=Decimal("0.90"),
        max_escape_defects=0,
        require_idempotence=True,
        require_adversarial_fixtures=True,
        require_owner_signature=True,
    ),
}

#: The only legal transitions.  Nothing skips a rung upward; anything may be
#: deprecated, and anything may be revoked.
_TRANSITIONS: Mapping[RecipeStatus, frozenset[RecipeStatus]] = {
    RecipeStatus.DRAFT: frozenset({RecipeStatus.QUARANTINED, RecipeStatus.DEPRECATED, RecipeStatus.REVOKED}),
    RecipeStatus.QUARANTINED: frozenset(
        {RecipeStatus.VERIFIED, RecipeStatus.DRAFT, RecipeStatus.DEPRECATED, RecipeStatus.REVOKED}
    ),
    RecipeStatus.VERIFIED: frozenset(
        {RecipeStatus.CERTIFIED, RecipeStatus.QUARANTINED, RecipeStatus.DEPRECATED, RecipeStatus.REVOKED}
    ),
    RecipeStatus.CERTIFIED: frozenset(
        {RecipeStatus.VERIFIED, RecipeStatus.QUARANTINED, RecipeStatus.DEPRECATED, RecipeStatus.REVOKED}
    ),
    RecipeStatus.DEPRECATED: frozenset({RecipeStatus.REVOKED}),
    #: Terminal.  A revoked digest is never resurrected; a fixed Recipe is a
    #: new version with a new digest.
    RecipeStatus.REVOKED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Fixture:
    fixture_id: str
    kind: FixtureKind
    language: str
    provenance: Provenance
    repository_id: str
    before: str
    expected_after: str
    #: Set by the corpus owner when a customer explicitly permitted sharing.
    sharing_grant: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "fixtureId": self.fixture_id,
            "kind": self.kind.value,
            "language": self.language,
            "provenance": self.provenance.value,
            "repositoryId": self.repository_id,
            "sharingGrant": self.sharing_grant,
            "beforeDigest": sha256_payload({"text": self.before}),
            "afterDigest": sha256_payload({"text": self.expected_after}),
        }


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    """The measured behaviour of one Recipe on one corpus."""

    recipe_reference: str
    recipe_digest: str
    corpus_digest: str
    true_positives: int
    false_positives: int
    false_negatives: int
    escape_defects: int
    idempotent: bool
    repositories: tuple[str, ...]
    adversarial_fixtures: int
    cost_units: Decimal = Decimal(0)

    @property
    def precision(self) -> Decimal | None:
        total = self.true_positives + self.false_positives
        if total == 0:
            #: Nothing fired.  Precision is undefined, not perfect.
            return None
        return Decimal(self.true_positives) / Decimal(total)

    @property
    def recall(self) -> Decimal | None:
        total = self.true_positives + self.false_negatives
        if total == 0:
            return None
        return Decimal(self.true_positives) / Decimal(total)

    def to_payload(self) -> dict[str, Any]:
        return {
            "recipe": self.recipe_reference,
            "recipeDigest": self.recipe_digest,
            "corpusDigest": self.corpus_digest,
            "truePositives": self.true_positives,
            "falsePositives": self.false_positives,
            "falseNegatives": self.false_negatives,
            "escapeDefects": self.escape_defects,
            "idempotent": self.idempotent,
            "precision": None if self.precision is None else str(self.precision),
            "recall": None if self.recall is None else str(self.recall),
            "distinctRepositories": len(set(self.repositories)),
            "adversarialFixtures": self.adversarial_fixtures,
            "costUnits": str(self.cost_units),
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    reference: str
    current: RecipeStatus
    requested: RecipeStatus
    granted: bool
    unmet: tuple[str, ...]
    rule: PromotionRule | None

    def to_payload(self) -> dict[str, Any]:
        return {
            "recipe": self.reference,
            "currentStatus": self.current.value,
            "requestedStatus": self.requested.value,
            "granted": self.granted,
            "unmetConditions": list(self.unmet),
            "rule": None if self.rule is None else self.rule.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class Revocation:
    recipe_digest: str
    reference: str
    reason: str
    severity: RiskClass
    reported_by: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "recipeDigest": self.recipe_digest,
            "recipe": self.reference,
            "reason": self.reason,
            "severity": self.severity.value,
            "reportedBy": self.reported_by,
        }


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    recipe: Recipe
    status: RecipeStatus
    evaluations: tuple[EvaluationReport, ...]
    signatures: tuple[Mapping[str, str], ...]
    owners: tuple[str, ...]

    @property
    def digest(self) -> str:
        return self.recipe.digest

    @property
    def executable(self) -> bool:
        return self.status not in (RecipeStatus.REVOKED, RecipeStatus.DEPRECATED)

    def to_payload(self) -> dict[str, Any]:
        return {
            "reference": self.recipe.reference,
            "digest": self.digest,
            "status": self.status.value,
            "languages": list(self.recipe.languages),
            "frameworks": list(self.recipe.frameworks),
            "riskClass": self.recipe.risk_class.value,
            "owners": list(self.owners),
            "evaluationCount": len(self.evaluations),
            "latestEvaluation": self.evaluations[-1].to_payload() if self.evaluations else None,
            "signatures": [dict(item) for item in self.signatures],
            "executable": self.executable,
        }


@dataclass
class RecipeRegistry:
    """An in-memory registry with the safety rules of a shared one.

    The store is a plain mapping so a host can persist it however it likes;
    what matters is that every mutation goes through the methods below, which
    is where the invariants live.
    """

    entries: dict[str, RegistryEntry] = field(default_factory=dict)
    revocations: dict[str, Revocation] = field(default_factory=dict)
    #: digest -> run ids that applied it, appended by the orchestrator.
    applications: dict[str, list[str]] = field(default_factory=dict)

    # -- registration ----------------------------------------------------

    def register(self, recipe: Recipe, *, owners: Sequence[str] = ()) -> RegistryEntry:
        """Add a Recipe at ``draft``; refuse to rebind an existing digest."""

        digest = recipe.digest
        if digest in self.revocations:
            raise ContractError(
                "recipe_revoked",
                f"digest {digest} is revoked and may not be registered again",
                {"reason": self.revocations[digest].reason},
            )
        existing = self.entries.get(digest)
        if existing is not None:
            raise ContractError(
                "recipe_already_registered",
                f"'{recipe.reference}' is already registered under digest {digest}; "
                "an edited Recipe is a new version, not an update to this one",
                {"status": existing.status.value},
            )
        for entry in self.entries.values():
            if entry.recipe.reference == recipe.reference:
                raise ContractError(
                    "recipe_version_collision",
                    f"reference '{recipe.reference}' is taken by digest {entry.digest}; "
                    "publish a new version rather than changing this one",
                    {"existingDigest": entry.digest, "candidateDigest": digest},
                )
        entry = RegistryEntry(
            recipe=recipe,
            status=RecipeStatus.DRAFT,
            evaluations=(),
            signatures=(),
            owners=tuple(owners) or recipe.owners,
        )
        self.entries[digest] = entry
        return entry

    def require(self, digest: str) -> RegistryEntry:
        entry = self.entries.get(digest)
        if entry is None:
            raise ContractError("recipe_not_registered", f"no Recipe is registered under {digest}")
        return entry

    # -- evaluation ------------------------------------------------------

    def record_evaluation(self, digest: str, report: EvaluationReport) -> RegistryEntry:
        entry = self.require(digest)
        if report.recipe_digest != digest:
            raise ContractError(
                "evaluation_digest_mismatch",
                "an evaluation may only be attached to the exact Recipe it measured",
                {"evaluated": report.recipe_digest, "target": digest},
            )
        updated = RegistryEntry(
            recipe=entry.recipe,
            status=entry.status,
            evaluations=(*entry.evaluations, report),
            signatures=entry.signatures,
            owners=entry.owners,
        )
        self.entries[digest] = updated
        return updated

    def sign(self, digest: str, *, subject: str, role: str) -> RegistryEntry:
        entry = self.require(digest)
        if subject in {item.get("subject") for item in entry.signatures}:
            return entry
        updated = RegistryEntry(
            recipe=entry.recipe,
            status=entry.status,
            evaluations=entry.evaluations,
            signatures=(*entry.signatures, {"subject": subject, "role": role, "digest": digest}),
            owners=entry.owners,
        )
        self.entries[digest] = updated
        return updated

    # -- promotion -------------------------------------------------------

    def promote(self, digest: str, target: RecipeStatus) -> PromotionDecision:
        entry = self.require(digest)
        decision = evaluate_promotion(entry, target)
        if decision.granted:
            self.entries[digest] = RegistryEntry(
                recipe=entry.recipe,
                status=target,
                evaluations=entry.evaluations,
                signatures=entry.signatures,
                owners=entry.owners,
            )
        return decision

    # -- revocation ------------------------------------------------------

    def revoke(self, digest: str, *, reason: str, severity: RiskClass, reported_by: str) -> Revocation:
        entry = self.require(digest)
        record = Revocation(
            recipe_digest=digest,
            reference=entry.recipe.reference,
            reason=reason,
            severity=severity,
            reported_by=reported_by,
        )
        self.revocations[digest] = record
        self.entries[digest] = RegistryEntry(
            recipe=entry.recipe,
            status=RecipeStatus.REVOKED,
            evaluations=entry.evaluations,
            signatures=entry.signatures,
            owners=entry.owners,
        )
        return record

    def record_application(self, digest: str, run_id: str) -> None:
        self.applications.setdefault(digest, []).append(run_id)

    def affected_runs(self, digest: str) -> tuple[str, ...]:
        """Runs that already applied this Recipe — the reason revocation matters."""

        return tuple(sorted(set(self.applications.get(digest, ()))))

    def check_executable(self, digest: str) -> None:
        """Raise unless this exact digest may be executed right now."""

        entry = self.entries.get(digest)
        if entry is None:
            raise ContractError(
                "recipe_not_registered",
                f"digest {digest} is not in the registry; an unregistered Recipe has no evaluation "
                "history and may not be executed",
            )
        if digest in self.revocations:
            record = self.revocations[digest]
            raise ContractError(
                "recipe_revoked",
                f"'{entry.recipe.reference}' was revoked: {record.reason}",
                {"severity": record.severity.value, "affectedRuns": list(self.affected_runs(digest))},
            )
        if entry.status is RecipeStatus.DEPRECATED:
            raise ContractError(
                "recipe_deprecated",
                f"'{entry.recipe.reference}' is deprecated and may not start new executions",
            )

    # -- query -----------------------------------------------------------

    def query(
        self,
        *,
        language: str = "",
        framework: str = "",
        max_risk: RiskClass | None = None,
        minimum_status: RecipeStatus | None = None,
    ) -> tuple[RegistryEntry, ...]:
        order = list(RecipeStatus)
        found: list[RegistryEntry] = []
        for entry in self.entries.values():
            if not entry.executable:
                continue
            if language and language not in entry.recipe.languages:
                continue
            if framework and framework not in entry.recipe.frameworks:
                continue
            if max_risk is not None and _risk_rank(entry.recipe.risk_class) > _risk_rank(max_risk):
                continue
            if minimum_status is not None and order.index(entry.status) < order.index(minimum_status):
                continue
            found.append(entry)
        return tuple(sorted(found, key=lambda item: item.recipe.reference))

    def to_payload(self) -> dict[str, Any]:
        return {
            "recipes": [entry.to_payload() for entry in sorted(
                self.entries.values(), key=lambda item: item.recipe.reference
            )],
            "revocationList": [item.to_payload() for item in sorted(
                self.revocations.values(), key=lambda item: item.recipe_digest
            )],
        }


def _risk_rank(value: RiskClass) -> int:
    return list(RiskClass).index(value)


# ---------------------------------------------------------------------------
# Promotion adjudication
# ---------------------------------------------------------------------------


def evaluate_promotion(entry: RegistryEntry, target: RecipeStatus) -> PromotionDecision:
    """Report *every* unmet condition, not just the first."""

    unmet: list[str] = []
    allowed = _TRANSITIONS.get(entry.status, frozenset())
    if target not in allowed:
        return PromotionDecision(
            reference=entry.recipe.reference,
            current=entry.status,
            requested=target,
            granted=False,
            unmet=(
                f"'{entry.status.value}' -> '{target.value}' is not a legal transition; "
                f"legal targets are {sorted(item.value for item in allowed) or 'none'}",
            ),
            rule=None,
        )

    rule = PROMOTION_RULES.get(target)
    if rule is None:
        #: Deprecation and revocation need no evidence — only demotion does not
        #: require proof, because it never widens what a Recipe may do.
        return PromotionDecision(
            reference=entry.recipe.reference,
            current=entry.status,
            requested=target,
            granted=True,
            unmet=(),
            rule=None,
        )

    if not entry.evaluations:
        unmet.append("no evaluation has been recorded; a Recipe is promoted on measurements, not intent")
    repositories: set[str] = set()
    escapes = 0
    idempotent = True
    adversarial = 0
    precisions: list[Decimal] = []
    recalls: list[Decimal] = []
    for report in entry.evaluations:
        repositories.update(report.repositories)
        escapes += report.escape_defects
        idempotent = idempotent and report.idempotent
        adversarial += report.adversarial_fixtures
        if report.precision is not None:
            precisions.append(report.precision)
        if report.recall is not None:
            recalls.append(report.recall)

    if len(repositories) < rule.min_distinct_repositories:
        unmet.append(
            f"measured on {len(repositories)} distinct repository/repositories; "
            f"{rule.min_distinct_repositories} required — one success is not a track record"
        )
    if not precisions:
        unmet.append("precision is undefined: the Recipe never fired on the corpus")
    else:
        worst = min(precisions)
        if worst < rule.min_precision:
            unmet.append(f"worst measured precision {worst} is below the required {rule.min_precision}")
    if not recalls:
        unmet.append("recall is undefined: the corpus contains no case this Recipe should have matched")
    else:
        worst_recall = min(recalls)
        if worst_recall < rule.min_recall:
            unmet.append(f"worst measured recall {worst_recall} is below the required {rule.min_recall}")
    if escapes > rule.max_escape_defects:
        unmet.append(
            f"{escapes} escape defect(s): the Recipe changed something outside its declared scope, "
            "which no success rate compensates for"
        )
    if rule.require_idempotence and not idempotent:
        unmet.append("the Recipe is not idempotent; a second application changes the result again")
    if rule.require_adversarial_fixtures and adversarial < 1:
        unmet.append("no adversarial fixture was evaluated; the corpus only proves the easy cases")
    if rule.require_owner_signature and not entry.signatures:
        unmet.append("no owner signature is attached")
    if rule.require_owner_signature and not entry.owners:
        unmet.append("the Recipe declares no owner, so there is nobody to hold responsible for it")

    return PromotionDecision(
        reference=entry.recipe.reference,
        current=entry.status,
        requested=target,
        granted=not unmet,
        unmet=tuple(unmet),
        rule=rule,
    )


def admit_fixture(fixture: Fixture) -> None:
    """Refuse a corpus fixture whose provenance does not permit sharing."""

    if fixture.provenance is Provenance.CUSTOMER and not fixture.sharing_grant.strip():
        raise ContractError(
            "fixture_not_shareable",
            f"fixture '{fixture.fixture_id}' comes from customer repository "
            f"'{fixture.repository_id}' with no sharing grant; customer code does not enter a "
            "shared corpus by default",
            {"repositoryId": fixture.repository_id},
        )


def corpus_digest(fixtures: Sequence[Fixture]) -> str:
    """Identity of the corpus a report was measured against."""

    return sha256_payload(
        {"fixtures": [item.to_payload() for item in sorted(fixtures, key=lambda entry: entry.fixture_id)]}
    )


def publish_version(registry: RecipeRegistry, recipe: Recipe, *, owners: Sequence[str] = ()) -> RegistryEntry:
    """Register a Recipe as a *new version*, refusing a silent in-place edit."""

    for entry in registry.entries.values():
        if entry.recipe.name == recipe.name and entry.recipe.version == recipe.version:
            if entry.digest == recipe.digest:
                return entry
            raise ContractError(
                "recipe_version_reused",
                f"version '{recipe.version}' of '{recipe.name}' already exists with a different "
                "digest; a changed Recipe needs a new version string",
                {"existingDigest": entry.digest, "candidateDigest": recipe.digest},
            )
    return registry.register(recipe, owners=owners)


__all__ = [
    "PROMOTION_RULES",
    "EvaluationReport",
    "Fixture",
    "FixtureKind",
    "PromotionDecision",
    "PromotionRule",
    "Provenance",
    "RecipeRegistry",
    "RegistryEntry",
    "Revocation",
    "admit_fixture",
    "corpus_digest",
    "evaluate_promotion",
    "publish_version",
]
