"""Capability package registry: immutable versions, earned promotions, real semver.

A capability package is executable authority — workflows, tools, hooks, policies
and verifiers that will run against a repository.  Three properties make that
safe, and each one is here because its absence is a known way to lose control of
a fleet.

Versions are immutable.  Republishing ``1.4.0`` with different bytes raises
``VERSION_IMMUTABLE`` rather than updating the entry, because every lock file,
every attestation and every incident report that names ``1.4.0`` is a claim
about specific content, and a mutable version turns all of them into fiction.

Promotion up the ladder — draft, candidate, approved, deprecated, revoked — is
earned, not asserted.  Each target stage declares the evidence kinds it requires
and demands a *passing* conformance report, where passing means the checks ran
and all of them passed; a report with zero checks is not a pass, it is a report
that measured nothing.

Dependency resolution is a real semver implementation, and a conflict is
reported rather than resolved.  "Pick the newer one" is the single most common
resolver behaviour and it is a policy decision disguised as an algorithm: the
two clashing constraints are named so a human can decide which one is wrong.

Revocation propagates.  Marking one version bad and stopping there is security
theatre — the point of a revocation is the fleet that already installed it, so
every installation that transitively depends on the revoked version is marked
``requires_action`` and listed by name.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from .contracts import (
    canonical_json,
    digest,
    format_timestamp,
    reject_unknown_fields,
    require_identifier,
    require_int,
    require_mapping,
    require_str,
    require_str_seq,
)
from .errors import Category, KernelError, register_codes
from .evidence import EvidenceKind
from .ports import Clock, EventStore
from .registry import register

__all__ = [
    "Comparator",
    "ConformanceReport",
    "Dependency",
    "InstallPlan",
    "Installation",
    "Package",
    "PackageRegistry",
    "PermissionReview",
    "PromotionDecision",
    "RegistryEntry",
    "Requirement",
    "Resolution",
    "Revocation",
    "Stage",
    "VersionRange",
    "Version",
    "bind_registry",
    "bound_registry",
    "default_signing_key",
    "handle",
    "record_promotion",
    "required_evidence_for",
    "resolve",
    "review_permissions",
    "set_default_signing_key",
    "sign_package",
]

register_codes(
    Category.INPUT,
    "PACKAGE_INVALID",
    "VERSION_UNPARSEABLE",
)
register_codes(
    Category.INTEGRITY,
    "SIGNATURE_INVALID",
    "VERSION_IMMUTABLE",
    "REVOCATION_INCOMPLETE",
)
register_codes(
    Category.SEMANTIC,
    "DEPENDENCY_CONFLICT",
    "DEPENDENCY_UNRESOLVED",
    "RUNTIME_INCOMPATIBLE",
    "PACKAGE_NOT_FOUND",
    "REGISTRY_UNCONFIGURED",
)
register_codes(
    Category.RELEASE,
    "ILLEGAL_PROMOTION",
    "PROMOTION_EVIDENCE_MISSING",
    "CONFORMANCE_FAILED",
    "PACKAGE_REVOKED",
)
register_codes(
    Category.POLICY,
    "PERMISSION_REVIEW_FAILED",
)


# --- semantic versions -------------------------------------------------------

_VERSION_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?"
    r"(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)
_NUMERIC_RE = re.compile(r"^(0|[1-9]\d*)$")


@dataclass(frozen=True, slots=True, order=False)
class Version:
    """A semantic version with real precedence rules.

    Build metadata is parsed and preserved but excluded from precedence, per
    the specification.  Prerelease identifiers compare numerically when they
    are numeric and lexically otherwise, and a prerelease always precedes the
    release it qualifies — the rule that makes ``1.0.0-rc.2 < 1.0.0`` and
    ``1.0.0-rc.9 < 1.0.0-rc.10``, both of which naive string comparison gets
    wrong.
    """

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: str = ""

    @classmethod
    def parse(cls, text: Any) -> Version:
        value = require_str(text, "version", max_length=256)
        matched = _VERSION_RE.match(value)
        if matched is None:
            raise KernelError(
                code="VERSION_UNPARSEABLE",
                message=f"{value!r} is not a semantic version",
                recommended_action="use MAJOR.MINOR.PATCH[-prerelease][+build]",
                details={"version": value},
            )
        prerelease = matched.group("prerelease")
        return cls(
            major=int(matched.group("major")),
            minor=int(matched.group("minor")),
            patch=int(matched.group("patch")),
            prerelease=tuple(prerelease.split(".")) if prerelease else (),
            build=matched.group("build") or "",
        )

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    @property
    def precedence(self) -> tuple[Any, ...]:
        """Comparison key per the semver precedence rules, build metadata excluded."""

        # A release outranks any prerelease of the same core, so the release
        # gets a sentinel that sorts after every identifier list.
        if not self.prerelease:
            return (self.major, self.minor, self.patch, 1, ())
        parts: list[tuple[int, Any]] = []
        for identifier in self.prerelease:
            if _NUMERIC_RE.match(identifier):
                parts.append((0, int(identifier)))
            else:
                parts.append((1, identifier))
        return (self.major, self.minor, self.patch, 0, tuple(parts))

    def __lt__(self, other: Version) -> bool:
        return self.precedence < other.precedence

    def __le__(self, other: Version) -> bool:
        return self.precedence <= other.precedence

    def __gt__(self, other: Version) -> bool:
        return self.precedence > other.precedence

    def __ge__(self, other: Version) -> bool:
        return self.precedence >= other.precedence

    def to_text(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(self.prerelease)
        if self.build:
            text += "+" + self.build
        return text

    def __str__(self) -> str:
        return self.to_text()


@dataclass(frozen=True, slots=True)
class Comparator:
    """One ``<op> <version>`` clause of a range."""

    op: str
    version: Version

    def __post_init__(self) -> None:
        if self.op not in {"=", ">", ">=", "<", "<="}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown comparator {self.op!r}",
                recommended_action="use one of = > >= < <=",
            )

    def allows(self, version: Version) -> bool:
        if self.op == "=":
            return version.precedence == self.version.precedence
        if self.op == ">":
            return version > self.version
        if self.op == ">=":
            return version >= self.version
        if self.op == "<":
            return version < self.version
        return version <= self.version

    def to_text(self) -> str:
        return f"{self.op}{self.version.to_text()}"


_RANGE_CLAUSE_RE = re.compile(r"^(?P<op>\^|~|>=|<=|>|<|=)?\s*(?P<version>.+)$")


@dataclass(frozen=True, slots=True)
class VersionRange:
    """A conjunction of comparators, parsed from ``^``, ``~``, ``>=``, ``<`` or exact.

    A prerelease only satisfies a range when some comparator names a
    prerelease of the same core version.  Without that rule ``>=1.0.0`` quietly
    admits ``2.0.0-alpha.1``, and a fleet upgrades itself onto an alpha.
    """

    text: str
    comparators: tuple[Comparator, ...]

    @classmethod
    def parse(cls, text: Any) -> VersionRange:
        value = require_str(text, "range", max_length=256).strip()
        if value in {"*", "any"}:
            return cls(text=value, comparators=(Comparator(">=", Version(0, 0, 0)),))
        clauses: list[Comparator] = []
        for raw in value.split():
            matched = _RANGE_CLAUSE_RE.match(raw.strip())
            if matched is None:
                raise KernelError(
                    code="VERSION_UNPARSEABLE",
                    message=f"{raw!r} is not a version range clause",
                    recommended_action="use ^1.2.3, ~1.2.3, >=1.2.3, <2.0.0 or 1.2.3",
                )
            op = matched.group("op") or "="
            version = Version.parse(matched.group("version"))
            if op == "^":
                clauses.append(Comparator(">=", version))
                clauses.append(Comparator("<", _caret_ceiling(version)))
            elif op == "~":
                clauses.append(Comparator(">=", version))
                clauses.append(Comparator("<", Version(version.major, version.minor + 1, 0)))
            else:
                clauses.append(Comparator(op, version))
        if not clauses:
            raise KernelError(
                code="VERSION_UNPARSEABLE",
                message="an empty range matches nothing and is refused",
                recommended_action="state a range, or use '*' deliberately",
            )
        return cls(text=value, comparators=tuple(clauses))

    def allows(self, version: Version) -> bool:
        if version.is_prerelease and not any(
            item.version.is_prerelease and item.version.core == version.core
            for item in self.comparators
        ):
            return False
        return all(item.allows(version) for item in self.comparators)

    def to_payload(self) -> dict[str, Any]:
        return {"text": self.text,
                "comparators": [item.to_text() for item in self.comparators]}


def _caret_ceiling(version: Version) -> Version:
    """``^`` allows changes that do not modify the left-most non-zero digit."""

    if version.major > 0:
        return Version(version.major + 1, 0, 0)
    if version.minor > 0:
        return Version(0, version.minor + 1, 0)
    return Version(0, 0, version.patch + 1)


# --- packages ----------------------------------------------------------------


class Stage(StrEnum):
    """Where a version sits on the promotion ladder."""

    DRAFT = "draft"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    DEPRECATED = "deprecated"
    REVOKED = "revoked"


#: Legal one-step promotions.  Revocation is *not* here: pulling a package is
#: always permitted and is handled by :meth:`PackageRegistry.revoke`, so a
#: safety action never has to walk a ladder to reach the fleet.
_LADDER: Mapping[Stage, tuple[Stage, ...]] = {
    Stage.DRAFT: (Stage.CANDIDATE,),
    Stage.CANDIDATE: (Stage.APPROVED,),
    Stage.APPROVED: (Stage.DEPRECATED,),
    Stage.DEPRECATED: (),
    Stage.REVOKED: (),
}

#: Evidence each target stage demands.  These grow monotonically along the
#: ladder for the same reason security tiers do.
_REQUIRED_EVIDENCE: Mapping[Stage, tuple[EvidenceKind, ...]] = {
    Stage.CANDIDATE: (EvidenceKind.TEST_REPORT,),
    Stage.APPROVED: (EvidenceKind.TEST_REPORT, EvidenceKind.POLICY_DECISION,
                     EvidenceKind.ARTIFACT_HASH, EvidenceKind.EXECUTION_TRACE),
    Stage.DEPRECATED: (EvidenceKind.POLICY_DECISION,),
}


def required_evidence_for(stage: Stage) -> tuple[EvidenceKind, ...]:
    """Evidence kinds required to enter ``stage``."""

    return _REQUIRED_EVIDENCE.get(stage, ())


@dataclass(frozen=True, slots=True)
class Dependency:
    """A dependency on another package, expressed as a range."""

    package_id: str
    range: VersionRange

    def to_payload(self) -> dict[str, Any]:
        return {"packageId": self.package_id, "range": self.range.text}


@dataclass(frozen=True, slots=True)
class Package:
    """An immutable, signed capability package at one version."""

    package_id: str
    version: Version
    skills: tuple[str, ...]
    contracts_digest: str
    provenance: Mapping[str, Any]
    signature: str
    dependencies: tuple[Dependency, ...] = ()
    permissions: Mapping[str, Any] = field(default_factory=dict)
    component_paths: tuple[str, ...] = ()
    kernel_range: str = "*"

    def __post_init__(self) -> None:
        require_identifier(self.package_id, "package.package_id")
        if not isinstance(self.version, Version):
            raise KernelError(
                code="PACKAGE_INVALID",
                message="package.version must be a parsed Version",
                recommended_action="use Version.parse before constructing a Package",
            )
        if not self.skills:
            raise KernelError(
                code="PACKAGE_INVALID",
                message=f"package {self.package_id!r} declares no skills",
                recommended_action="a package with no capabilities is not installable",
            )
        for index, skill in enumerate(self.skills):
            require_identifier(skill, f"package.skills[{index}]")
        require_str(self.contracts_digest, "package.contracts_digest", max_length=256)
        require_str(self.signature, "package.signature", max_length=512)
        for index, path in enumerate(self.component_paths):
            text = require_str(path, f"package.component_paths[{index}]", max_length=1024)
            if text.startswith("/") or ".." in text.split("/"):
                raise KernelError(
                    code="PACKAGE_INVALID",
                    message=(
                        f"component path {text!r} escapes the package root; paths are "
                        "relative to the package root and may not traverse upwards"
                    ),
                    recommended_action="use a path relative to the package root",
                    details={"path": text},
                )
        VersionRange.parse(self.kernel_range)

    @property
    def content(self) -> dict[str, Any]:
        """Exactly what the version's identity and signature cover."""

        return {
            "packageId": self.package_id,
            "version": self.version.to_text(),
            "skills": sorted(self.skills),
            "contractsDigest": self.contracts_digest,
            "dependencies": [item.to_payload() for item in sorted(
                self.dependencies, key=lambda item: item.package_id)],
            "permissions": dict(self.permissions),
            "componentPaths": sorted(self.component_paths),
            "kernelRange": self.kernel_range,
        }

    @property
    def content_digest(self) -> str:
        return digest(self.content)

    def to_payload(self) -> dict[str, Any]:
        return self.content | {
            "provenance": dict(self.provenance),
            "signature": self.signature,
            "contentDigest": self.content_digest,
        }


def sign_package(content_digest: str, key: bytes) -> str:
    """HMAC over the content digest.

    The key is a secret and never enters a payload, a log line or an error
    message; only the resulting tag travels.
    """

    return "hmac-sha256:" + hmac.new(key, content_digest.encode("utf-8"), sha256).hexdigest()


# --- reviews and reports -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class PermissionReview:
    """Default-deny review of what a package asks for.

    A wildcard grant is denied unless it appears in the explicit approval list.
    "Everything" is never an accident worth honouring.
    """

    package_id: str
    version: str
    requested: tuple[tuple[str, str], ...]
    wildcards: tuple[str, ...]
    approved_wildcards: tuple[str, ...]
    denied: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.denied

    def to_payload(self) -> dict[str, Any]:
        return {
            "packageId": self.package_id,
            "version": self.version,
            "requested": [[name, value] for name, value in self.requested],
            "wildcards": list(self.wildcards),
            "approvedWildcards": list(self.approved_wildcards),
            "denied": list(self.denied),
            "passed": self.passed,
        }


def review_permissions(package: Package, *,
                       approved_wildcards: Sequence[str] = ()) -> PermissionReview:
    """Flatten a package's permission block and deny unapproved wildcards."""

    requested: list[tuple[str, str]] = []
    wildcards: list[str] = []
    for name in sorted(package.permissions):
        value = package.permissions[name]
        rendered = value if isinstance(value, str) else canonical_json(value)
        requested.append((name, rendered))
        if "*" in rendered:
            wildcards.append(name)
    approved = tuple(sorted(set(approved_wildcards)))
    denied = tuple(sorted(name for name in wildcards if name not in approved))
    return PermissionReview(
        package_id=package.package_id,
        version=package.version.to_text(),
        requested=tuple(requested),
        wildcards=tuple(sorted(wildcards)),
        approved_wildcards=approved,
        denied=denied,
    )


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """The result of running the release conformance suite against a package.

    ``checks_total`` of zero is not a pass.  A suite that ran no checks
    measured nothing, and "no failures" over an empty set is the most
    convincing false positive in software.
    """

    report_id: str
    package_id: str
    version: str
    checks_total: int
    checks_passed: int
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.report_id, "conformance.report_id")
        require_int(self.checks_total, "conformance.checks_total", minimum=0)
        require_int(self.checks_passed, "conformance.checks_passed", minimum=0)
        if self.checks_passed > self.checks_total:
            raise KernelError(
                code="CONFORMANCE_FAILED",
                message="conformance report passes more checks than it ran",
                recommended_action="treat the report as corrupt",
            )

    @property
    def passed(self) -> bool:
        return self.checks_total > 0 and self.checks_passed == self.checks_total

    def to_payload(self) -> dict[str, Any]:
        return {
            "reportId": self.report_id,
            "packageId": self.package_id,
            "version": self.version,
            "checksTotal": self.checks_total,
            "checksPassed": self.checks_passed,
            "passed": self.passed,
            "evidenceIds": list(self.evidence_ids),
        }


# --- resolution --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Requirement:
    """One constraint, attributed to whoever asked for it."""

    requester: str
    package_id: str
    range: VersionRange

    def to_payload(self) -> dict[str, Any]:
        return {"requester": self.requester, "packageId": self.package_id,
                "range": self.range.text}


@dataclass(frozen=True, slots=True)
class Resolution:
    """The resolved versions, or the constraints that made resolution impossible."""

    resolved: tuple[tuple[str, str], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    unresolved: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.conflicts and not self.unresolved

    def to_payload(self) -> dict[str, Any]:
        return {
            "resolved": [[name, version] for name, version in self.resolved],
            "conflicts": [dict(item) for item in self.conflicts],
            "unresolved": list(self.unresolved),
            "ok": self.ok,
        }


def resolve(requirements: Sequence[Requirement],
            available: Mapping[str, Sequence[Version]]) -> Resolution:
    """Resolve every requirement deterministically, or report the clash.

    Selection is "the highest version satisfying every constraint", which is
    deterministic given the same catalogue.  When no version satisfies all of
    them, the resolver does *not* drop a constraint to make progress: it looks
    for the two constraints that cannot both hold and names them, falling back
    to the whole constraint set when the clash is genuinely n-way.
    """

    by_package: dict[str, list[Requirement]] = {}
    for requirement in requirements:
        by_package.setdefault(requirement.package_id, []).append(requirement)

    resolved: list[tuple[str, str]] = []
    conflicts: list[Mapping[str, Any]] = []
    unresolved: list[str] = []

    for package_id in sorted(by_package):
        constraints = by_package[package_id]
        candidates = sorted(available.get(package_id, ()), key=lambda item: item.precedence)
        if not candidates:
            unresolved.append(package_id)
            continue
        satisfying = [item for item in candidates
                      if all(req.range.allows(item) for req in constraints)]
        if satisfying:
            resolved.append((package_id, satisfying[-1].to_text()))
            continue
        conflicts.append(_describe_conflict(package_id, constraints, candidates))

    return Resolution(resolved=tuple(resolved), conflicts=tuple(conflicts),
                      unresolved=tuple(sorted(unresolved)))


def _describe_conflict(package_id: str, constraints: Sequence[Requirement],
                       candidates: Sequence[Version]) -> Mapping[str, Any]:
    """Name the two constraints that cannot both be satisfied, when there are two."""

    for index, left in enumerate(constraints):
        for right in constraints[index + 1:]:
            if not any(left.range.allows(item) and right.range.allows(item)
                       for item in candidates):
                return {
                    "packageId": package_id,
                    "kind": "PAIRWISE",
                    "left": left.to_payload(),
                    "right": right.to_payload(),
                    "candidates": [item.to_text() for item in candidates],
                    "detail": (
                        f"{left.requester} requires {left.range.text} and "
                        f"{right.requester} requires {right.range.text}; no published "
                        f"version of {package_id} satisfies both"
                    ),
                }
    # Interval ranges over a totally ordered version set always admit a
    # pairwise witness when they are jointly unsatisfiable, so this branch is
    # defensive: it exists so that a future non-interval constraint kind
    # reports the whole set rather than silently resolving.
    return {
        "packageId": package_id,
        "kind": "NARY",
        "constraints": [item.to_payload() for item in constraints],
        "candidates": [item.to_text() for item in candidates],
        "detail": (
            f"every pair of constraints on {package_id} is individually satisfiable but "
            "no single version satisfies all of them"
        ),
    }


# --- registry state ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """One published version and where it sits on the ladder."""

    package: Package
    stage: Stage
    published_at: datetime
    promoted_at: datetime
    evidence_ids: tuple[str, ...] = ()
    revocation_reason: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "package": self.package.to_payload(),
            "stage": str(self.stage),
            "publishedAt": format_timestamp(self.published_at),
            "promotedAt": format_timestamp(self.promoted_at),
            "evidenceIds": list(self.evidence_ids),
            "revocationReason": self.revocation_reason,
        }


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    """Whether a promotion was granted, and exactly what it required."""

    package_id: str
    version: str
    from_stage: Stage
    to_stage: Stage
    granted: bool
    required_evidence: tuple[str, ...]
    supplied_evidence: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    conformance: Mapping[str, Any] | None
    approver: str
    decided_at: datetime
    detail: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "packageId": self.package_id,
            "version": self.version,
            "fromStage": str(self.from_stage),
            "toStage": str(self.to_stage),
            "granted": self.granted,
            "requiredEvidence": list(self.required_evidence),
            "suppliedEvidence": list(self.supplied_evidence),
            "missingEvidence": list(self.missing_evidence),
            "conformance": None if self.conformance is None else dict(self.conformance),
            "approver": self.approver,
            "decidedAt": format_timestamp(self.decided_at),
            "detail": self.detail,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class InstallPlan:
    """What installing a set of requirements would change.

    ``idempotent`` is true when applying the plan again would do nothing, which
    is the property the orchestrator relies on when it retries a step after an
    ambiguous failure.
    """

    installation_id: str
    resolution: Resolution
    to_install: tuple[tuple[str, str], ...]
    already_satisfied: tuple[tuple[str, str], ...]
    to_replace: tuple[tuple[str, str, str], ...]
    blocked: tuple[Mapping[str, Any], ...]

    @property
    def idempotent(self) -> bool:
        return not self.to_install and not self.to_replace

    def to_payload(self) -> dict[str, Any]:
        return {
            "installationId": self.installation_id,
            "resolution": self.resolution.to_payload(),
            "toInstall": [[name, version] for name, version in self.to_install],
            "alreadySatisfied": [[name, version] for name, version in self.already_satisfied],
            "toReplace": [[name, before, after] for name, before, after in self.to_replace],
            "blocked": [dict(item) for item in self.blocked],
            "idempotent": self.idempotent,
            "digest": digest({
                "installationId": self.installation_id,
                "toInstall": [[name, version] for name, version in self.to_install],
                "toReplace": [[name, before, after] for name, before, after in self.to_replace],
            }),
        }


@dataclass(frozen=True, slots=True)
class Installation:
    """A fleet member's installed set and the edges between its packages."""

    installation_id: str
    packages: tuple[tuple[str, str], ...]
    edges: tuple[tuple[str, str], ...] = ()

    def dependents_of(self, package_id: str) -> tuple[str, ...]:
        """Transitive closure of "depends on ``package_id``"."""

        reverse: dict[str, list[str]] = {}
        for dependent, dependency in self.edges:
            reverse.setdefault(dependency, []).append(dependent)
        seen: set[str] = set()
        stack = list(reverse.get(package_id, ()))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(reverse.get(node, ()))
        return tuple(sorted(seen))

    def to_payload(self) -> dict[str, Any]:
        return {
            "installationId": self.installation_id,
            "packages": [[name, version] for name, version in self.packages],
            "edges": [[a, b] for a, b in self.edges],
        }


@dataclass(frozen=True, slots=True)
class Revocation:
    """A revocation and everything it reaches."""

    package_id: str
    version: str
    reason: str
    approver: str
    revoked_at: datetime
    affected_installations: tuple[str, ...]
    requires_action: tuple[tuple[str, str, str], ...]

    @property
    def propagated(self) -> bool:
        return bool(self.affected_installations)

    def to_payload(self) -> dict[str, Any]:
        return {
            "packageId": self.package_id,
            "version": self.version,
            "reason": self.reason,
            "approver": self.approver,
            "revokedAt": format_timestamp(self.revoked_at),
            "affectedInstallations": list(self.affected_installations),
            "requiresAction": [[installation, name, version]
                               for installation, name, version in self.requires_action],
            "propagated": self.propagated,
        }

    @property
    def digest(self) -> str:
        return digest(self.to_payload())


class PackageRegistry:
    """Publication, promotion, resolution, installation and revocation.

    All state is held here rather than in module globals so that two registries
    (a staging one and a production one, say) cannot contaminate each other, and
    so that a test can build one from scratch in a line.
    """

    __slots__ = ("_clock", "_signing_key", "_entries", "_installations",
                 "_requires_action", "_approved_wildcards", "_kernel_version")

    def __init__(self, *, clock: Clock, signing_key: bytes,
                 kernel_version: str = "2.0.0",
                 approved_wildcards: Sequence[str] = ()) -> None:
        self._clock = clock
        self._signing_key = bytes(signing_key)
        self._entries: dict[tuple[str, str], RegistryEntry] = {}
        self._installations: dict[str, Installation] = {}
        self._requires_action: dict[tuple[str, str, str], str] = {}
        self._approved_wildcards = tuple(sorted(set(approved_wildcards)))
        self._kernel_version = Version.parse(kernel_version)

    # -- publication ----------------------------------------------------------

    def publish(self, package: Package) -> RegistryEntry:
        """Publish a version, or refuse to change one that already exists.

        Republishing byte-identical content is idempotent and returns the
        existing entry.  Republishing *different* content under the same
        version raises ``VERSION_IMMUTABLE`` and names both digests.
        """

        self._verify_signature(package)
        review = review_permissions(package, approved_wildcards=self._approved_wildcards)
        if not review.passed:
            raise KernelError(
                code="PERMISSION_REVIEW_FAILED",
                message=(
                    f"package {package.package_id}@{package.version} requests wildcard "
                    f"permissions {list(review.denied)} that were not explicitly approved"
                ),
                retryable=False,
                recommended_action="narrow the permissions or approve each wildcard by name",
                details={"permissionReview": review.to_payload()},
            )
        if not VersionRange.parse(package.kernel_range).allows(self._kernel_version):
            raise KernelError(
                code="RUNTIME_INCOMPATIBLE",
                message=(
                    f"package {package.package_id}@{package.version} requires kernel "
                    f"{package.kernel_range}; this kernel is {self._kernel_version}"
                ),
                retryable=False,
                recommended_action="publish against a kernel the package supports",
            )

        key = (package.package_id, package.version.to_text())
        existing = self._entries.get(key)
        if existing is not None:
            if existing.package.content_digest != package.content_digest:
                raise KernelError(
                    code="VERSION_IMMUTABLE",
                    message=(
                        f"{package.package_id}@{package.version} is already published with "
                        f"content {existing.package.content_digest}; the submitted content "
                        f"is {package.content_digest}"
                    ),
                    retryable=False,
                    recommended_action="publish a new version; a version's bytes never change",
                    details={
                        "packageId": package.package_id,
                        "version": package.version.to_text(),
                        "publishedDigest": existing.package.content_digest,
                        "submittedDigest": package.content_digest,
                    },
                )
            return existing

        now = self._clock.now()
        entry = RegistryEntry(package=package, stage=Stage.DRAFT, published_at=now,
                              promoted_at=now)
        self._entries[key] = entry
        return entry

    def _verify_signature(self, package: Package) -> None:
        expected = sign_package(package.content_digest, self._signing_key)
        if not hmac.compare_digest(expected, package.signature):
            raise KernelError(
                code="SIGNATURE_INVALID",
                message=(
                    f"signature on {package.package_id}@{package.version} does not cover "
                    "its content"
                ),
                retryable=False,
                recommended_action="re-sign the package; do not trust the claimed signature",
            )

    def entry(self, package_id: str, version: str) -> RegistryEntry:
        found = self._entries.get((package_id, version))
        if found is None:
            raise KernelError(
                code="PACKAGE_NOT_FOUND",
                message=f"{package_id}@{version} is not published",
                recommended_action="publish the version before referring to it",
            )
        return found

    def catalogue(self) -> Mapping[str, tuple[Version, ...]]:
        """Installable versions by package id.

        Draft and revoked versions are excluded: a draft was never promoted and
        a revoked one was withdrawn, and neither is a legitimate resolution
        target.
        """

        out: dict[str, list[Version]] = {}
        for (package_id, _), entry in sorted(self._entries.items()):
            if entry.stage in (Stage.DRAFT, Stage.REVOKED):
                continue
            out.setdefault(package_id, []).append(entry.package.version)
        return {name: tuple(sorted(versions, key=lambda item: item.precedence))
                for name, versions in out.items()}

    def component_catalogue(self) -> tuple[Mapping[str, Any], ...]:
        """Every published component, addressed by package, version and path."""

        return tuple(
            {
                "packageId": entry.package.package_id,
                "version": entry.package.version.to_text(),
                "stage": str(entry.stage),
                "skills": sorted(entry.package.skills),
                "componentPaths": sorted(entry.package.component_paths),
                "contractsDigest": entry.package.contracts_digest,
            }
            for _, entry in sorted(self._entries.items())
        )

    # -- promotion ------------------------------------------------------------

    def promote(self, package_id: str, version: str, target: Stage, *,
                evidence: Mapping[EvidenceKind, Sequence[str]] | None = None,
                conformance: ConformanceReport | None = None,
                approver: str) -> PromotionDecision:
        """Promote one step up the ladder, if the evidence for the target exists."""

        entry = self.entry(package_id, version)
        if target is Stage.REVOKED:
            raise KernelError(
                code="ILLEGAL_PROMOTION",
                message="revocation is not a promotion; call revoke()",
                recommended_action="use PackageRegistry.revoke",
            )
        if target not in _LADDER[entry.stage]:
            raise KernelError(
                code="ILLEGAL_PROMOTION",
                message=(
                    f"{package_id}@{version} is {entry.stage}; the only legal next stage "
                    f"is {[str(item) for item in _LADDER[entry.stage]] or 'none'}"
                ),
                retryable=False,
                recommended_action="promote one stage at a time",
                details={"from": str(entry.stage), "to": str(target)},
            )

        supplied = evidence or {}
        required = required_evidence_for(target)
        missing = tuple(sorted(str(kind) for kind in required if not supplied.get(kind)))
        now = self._clock.now()
        conformance_payload = None if conformance is None else conformance.to_payload()

        if missing:
            raise KernelError(
                code="PROMOTION_EVIDENCE_MISSING",
                message=(
                    f"promotion of {package_id}@{version} to {target} needs evidence "
                    f"{list(missing)}"
                ),
                retryable=False,
                recommended_action="produce the missing evidence and re-request promotion",
                details={"missingEvidence": list(missing),
                         "requiredEvidence": [str(kind) for kind in required]},
            )
        if conformance is None or not conformance.passed:
            raise KernelError(
                code="CONFORMANCE_FAILED",
                message=(
                    f"promotion of {package_id}@{version} to {target} requires a passing "
                    "conformance report"
                ),
                retryable=False,
                recommended_action="run the conformance suite until every check passes",
                details={"conformance": conformance_payload},
            )
        if conformance.package_id != package_id or conformance.version != version:
            raise KernelError(
                code="CONFORMANCE_FAILED",
                message=(
                    f"conformance report {conformance.report_id} is for "
                    f"{conformance.package_id}@{conformance.version}, not "
                    f"{package_id}@{version}"
                ),
                recommended_action="a report from another version proves nothing here",
            )

        collected = tuple(sorted({
            item for kind in required for item in supplied.get(kind, ())
        }))
        self._entries[(package_id, version)] = RegistryEntry(
            package=entry.package,
            stage=target,
            published_at=entry.published_at,
            promoted_at=now,
            evidence_ids=tuple(sorted(set(entry.evidence_ids) | set(collected))),
        )
        return PromotionDecision(
            package_id=package_id,
            version=version,
            from_stage=entry.stage,
            to_stage=target,
            granted=True,
            required_evidence=tuple(str(kind) for kind in required),
            supplied_evidence=collected,
            missing_evidence=(),
            conformance=conformance_payload,
            approver=approver,
            decided_at=now,
            detail=f"{package_id}@{version} promoted to {target}",
        )

    # -- installation ---------------------------------------------------------

    def install_plan(self, installation_id: str,
                     requirements: Sequence[Requirement]) -> InstallPlan:
        """Compute what installing ``requirements`` would change.

        Running the plan and re-planning yields an empty plan, which is what
        makes a retried install safe.
        """

        require_identifier(installation_id, "installation_id")
        resolution = resolve(requirements, self.catalogue())
        current = dict(self._installations.get(
            installation_id, Installation(installation_id, ())).packages)

        to_install: list[tuple[str, str]] = []
        satisfied: list[tuple[str, str]] = []
        replace: list[tuple[str, str, str]] = []
        blocked: list[Mapping[str, Any]] = []
        for package_id, version in resolution.resolved:
            entry = self._entries[(package_id, version)]
            if entry.stage is Stage.REVOKED:
                blocked.append({"packageId": package_id, "version": version,
                                "reason": "PACKAGE_REVOKED"})
                continue
            installed = current.get(package_id)
            if installed is None:
                to_install.append((package_id, version))
            elif installed == version:
                satisfied.append((package_id, version))
            else:
                replace.append((package_id, installed, version))
        return InstallPlan(
            installation_id=installation_id,
            resolution=resolution,
            to_install=tuple(sorted(to_install)),
            already_satisfied=tuple(sorted(satisfied)),
            to_replace=tuple(sorted(replace)),
            blocked=tuple(blocked),
        )

    def apply_plan(self, plan: InstallPlan) -> Installation:
        """Record the plan's outcome as the installation's new state."""

        if not plan.resolution.ok:
            raise KernelError(
                code="DEPENDENCY_CONFLICT",
                message=f"install plan for {plan.installation_id} did not resolve",
                retryable=False,
                recommended_action="resolve the reported conflicts before installing",
                details={"resolution": plan.resolution.to_payload()},
            )
        current = dict(self._installations.get(
            plan.installation_id, Installation(plan.installation_id, ())).packages)
        for package_id, version in plan.to_install:
            current[package_id] = version
        for package_id, _, version in plan.to_replace:
            current[package_id] = version
        edges: list[tuple[str, str]] = []
        for package_id, version in sorted(current.items()):
            entry = self._entries.get((package_id, version))
            if entry is None:
                continue
            for dependency in entry.package.dependencies:
                edges.append((package_id, dependency.package_id))
        installation = Installation(
            installation_id=plan.installation_id,
            packages=tuple(sorted(current.items())),
            edges=tuple(sorted(set(edges))),
        )
        self._installations[plan.installation_id] = installation
        return installation

    def installation(self, installation_id: str) -> Installation:
        found = self._installations.get(installation_id)
        if found is None:
            raise KernelError(
                code="PACKAGE_NOT_FOUND",
                message=f"installation {installation_id!r} is unknown",
                recommended_action="apply an install plan first",
            )
        return found

    def requires_action(self) -> tuple[tuple[str, str, str, str], ...]:
        """Every (installation, package, version, reason) awaiting a human."""

        return tuple(sorted(
            (installation, package_id, version, reason)
            for (installation, package_id, version), reason
            in self._requires_action.items()
        ))

    # -- revocation -----------------------------------------------------------

    def revoke(self, package_id: str, version: str, *, reason: str,
               approver: str) -> Revocation:
        """Revoke a version and mark every installed dependent.

        The propagation is the point.  A revocation that stops at the registry
        entry changes nothing about the machines that already installed the
        package, and a fleet that keeps running revoked code while a dashboard
        shows it as revoked is worse than one that never revoked it at all.
        """

        entry = self.entry(package_id, version)
        require_str(reason, "revocation.reason")
        require_str(approver, "revocation.approver", max_length=256)
        now = self._clock.now()
        self._entries[(package_id, version)] = RegistryEntry(
            package=entry.package,
            stage=Stage.REVOKED,
            published_at=entry.published_at,
            promoted_at=now,
            evidence_ids=entry.evidence_ids,
            revocation_reason=reason,
        )

        affected: list[str] = []
        actions: list[tuple[str, str, str]] = []
        for installation_id in sorted(self._installations):
            installation = self._installations[installation_id]
            installed = dict(installation.packages)
            if installed.get(package_id) != version:
                continue
            affected.append(installation_id)
            actions.append((installation_id, package_id, version))
            self._requires_action[(installation_id, package_id, version)] = (
                f"depends on revoked {package_id}@{version}: {reason}"
            )
            for dependent in installation.dependents_of(package_id):
                dependent_version = installed.get(dependent)
                if dependent_version is None:
                    continue
                actions.append((installation_id, dependent, dependent_version))
                self._requires_action[(installation_id, dependent, dependent_version)] = (
                    f"transitively depends on revoked {package_id}@{version}: {reason}"
                )

        revocation = Revocation(
            package_id=package_id,
            version=version,
            reason=reason,
            approver=approver,
            revoked_at=now,
            affected_installations=tuple(sorted(set(affected))),
            requires_action=tuple(sorted(set(actions))),
        )
        if affected and not revocation.requires_action:
            raise KernelError(
                code="REVOCATION_INCOMPLETE",
                message="revocation reached installations but marked nothing",
                recommended_action="treat as a kernel defect; do not report the fleet clean",
            )
        return revocation


# --- durable record ----------------------------------------------------------


def record_promotion(decision: PromotionDecision, events: EventStore, *, stream_id: str,
                     fencing_token: int) -> Mapping[str, Any]:
    """Append a promotion decision to the run log, idempotently and behind a fence."""

    event = events.append(
        stream_id,
        {"kind": "packreg.promotion", "promotion": decision.to_payload(),
         "promotionDigest": decision.digest},
        idempotency_key=decision.digest,
        fencing_token=fencing_token,
    )
    return {
        "sequence": event.sequence,
        "eventId": event.event_id,
        "hashChain": event.hash_chain,
        "promotionDigest": decision.digest,
    }


# --- registry entry point ----------------------------------------------------

_REGISTRY: PackageRegistry | None = None
_SIGNING_KEY: bytes | None = None


def bind_registry(registry: PackageRegistry | None) -> None:
    """Bind the process-wide package registry :func:`handle` operates on."""

    global _REGISTRY
    _REGISTRY = registry


def bound_registry() -> PackageRegistry:
    """Return the bound registry or fail closed."""

    if _REGISTRY is None:
        raise KernelError(
            code="REGISTRY_UNCONFIGURED",
            message="no package registry is bound in this process",
            recommended_action="call packreg.bind_registry at startup",
        )
    return _REGISTRY


def set_default_signing_key(key: bytes | None) -> None:
    """Bind the package signing key out of band.  It never travels in a request."""

    global _SIGNING_KEY
    _SIGNING_KEY = bytes(key) if key is not None else None


def default_signing_key() -> bytes:
    if _SIGNING_KEY is None:
        raise KernelError(
            code="SIGNATURE_INVALID",
            message="no package signing key is bound; signatures cannot be verified",
            recommended_action="bind the key with set_default_signing_key at startup",
        )
    return _SIGNING_KEY


def _decode_dependencies(raw: Any) -> tuple[Dependency, ...]:
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise KernelError(
            code="MALFORMED_INPUT",
            message="package.dependencies must be an array",
            recommended_action="supply dependencies as a JSON array",
        )
    out: list[Dependency] = []
    for item in raw:
        mapping = require_mapping(item, "dependency")
        reject_unknown_fields(mapping, {"packageId", "range"}, field_name="dependency")
        out.append(Dependency(
            package_id=require_identifier(mapping.get("packageId"), "dependency.packageId"),
            range=VersionRange.parse(mapping.get("range")),
        ))
    return tuple(out)


def _decode_package(payload: Mapping[str, Any]) -> Package:
    reject_unknown_fields(
        payload,
        {"packageId", "version", "skills", "contractsDigest", "provenance", "signature",
         "dependencies", "permissions", "componentPaths", "kernelRange"},
        field_name="package",
    )
    return Package(
        package_id=require_identifier(payload.get("packageId"), "package.packageId"),
        version=Version.parse(payload.get("version")),
        skills=require_str_seq(payload.get("skills", ()), "package.skills", allow_empty=False),
        contracts_digest=require_str(payload.get("contractsDigest"), "package.contractsDigest",
                                     max_length=256),
        provenance=require_mapping(payload.get("provenance", {}), "package.provenance"),
        signature=require_str(payload.get("signature"), "package.signature", max_length=512),
        dependencies=_decode_dependencies(payload.get("dependencies")),
        permissions=require_mapping(payload.get("permissions", {}), "package.permissions"),
        component_paths=require_str_seq(payload.get("componentPaths", ()),
                                        "package.componentPaths"),
        kernel_range=str(payload.get("kernelRange", "*")),
    )


def _decode_evidence(payload: Mapping[str, Any]) -> dict[EvidenceKind, tuple[str, ...]]:
    known = {kind.value for kind in EvidenceKind}
    out: dict[EvidenceKind, tuple[str, ...]] = {}
    for name in payload:
        if name not in known:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown evidence kind {name!r}",
                recommended_action=f"use one of {sorted(known)}",
            )
        out[EvidenceKind(name)] = require_str_seq(payload[name], f"evidence[{name}]")
    return out


def _decode_requirements(raw: Iterable[Any]) -> tuple[Requirement, ...]:
    out: list[Requirement] = []
    for item in raw:
        mapping = require_mapping(item, "requirement")
        reject_unknown_fields(mapping, {"requester", "packageId", "range"},
                              field_name="requirement")
        out.append(Requirement(
            requester=require_identifier(mapping.get("requester"), "requirement.requester"),
            package_id=require_identifier(mapping.get("packageId"), "requirement.packageId"),
            range=VersionRange.parse(mapping.get("range")),
        ))
    return tuple(out)


@register("capability-package-registry")
def handle(request: Mapping[str, Any]) -> Mapping[str, Any]:
    """Registry entry point.

    Publishes the supplied package, optionally promotes or revokes it, and
    always returns the install plan and permission review so that a caller
    cannot mistake "no error" for "nothing to do".  A refused promotion raises;
    it is never reported as a successful run with ``granted: false``.
    """

    reject_unknown_fields(
        request,
        {"package", "promotion_request", "evaluation_report", "requirements",
         "installation_id", "revocation_request"},
        field_name="capability-package-registry request",
    )
    registry = bound_registry()
    package = _decode_package(require_mapping(request.get("package"), "package"))
    entry = registry.publish(package)

    promotion: PromotionDecision | None = None
    promotion_payload = request.get("promotion_request")
    if promotion_payload is not None:
        mapping = require_mapping(promotion_payload, "promotion_request")
        reject_unknown_fields(mapping, {"toStage", "approver", "evidence"},
                              field_name="promotion_request")
        stage_text = require_str(mapping.get("toStage"), "promotion_request.toStage",
                                 max_length=32)
        if stage_text not in {item.value for item in Stage}:
            raise KernelError(
                code="MALFORMED_INPUT",
                message=f"unknown stage {stage_text!r}",
                recommended_action=f"use one of {sorted(item.value for item in Stage)}",
            )
        report_payload = require_mapping(request.get("evaluation_report", {}),
                                         "evaluation_report")
        reject_unknown_fields(report_payload,
                              {"reportId", "packageId", "version", "checksTotal",
                               "checksPassed", "evidenceIds"},
                              field_name="evaluation_report")
        conformance = None
        if report_payload:
            conformance = ConformanceReport(
                report_id=require_identifier(report_payload.get("reportId"),
                                             "evaluation_report.reportId"),
                package_id=require_identifier(report_payload.get("packageId"),
                                              "evaluation_report.packageId"),
                version=require_str(report_payload.get("version"),
                                    "evaluation_report.version", max_length=256),
                checks_total=require_int(report_payload.get("checksTotal"),
                                         "evaluation_report.checksTotal", minimum=0),
                checks_passed=require_int(report_payload.get("checksPassed"),
                                          "evaluation_report.checksPassed", minimum=0),
                evidence_ids=require_str_seq(report_payload.get("evidenceIds", ()),
                                             "evaluation_report.evidenceIds"),
            )
        promotion = registry.promote(
            package.package_id,
            package.version.to_text(),
            Stage(stage_text),
            evidence=_decode_evidence(require_mapping(mapping.get("evidence", {}),
                                                      "promotion_request.evidence")),
            conformance=conformance,
            approver=require_str(mapping.get("approver"), "promotion_request.approver",
                                 max_length=256),
        )
        entry = registry.entry(package.package_id, package.version.to_text())

    revocation: Revocation | None = None
    revocation_payload = request.get("revocation_request")
    if revocation_payload is not None:
        mapping = require_mapping(revocation_payload, "revocation_request")
        reject_unknown_fields(mapping, {"reason", "approver"},
                              field_name="revocation_request")
        revocation = registry.revoke(
            package.package_id,
            package.version.to_text(),
            reason=require_str(mapping.get("reason"), "revocation_request.reason"),
            approver=require_str(mapping.get("approver"), "revocation_request.approver",
                                 max_length=256),
        )
        entry = registry.entry(package.package_id, package.version.to_text())

    installation_id = require_identifier(request.get("installation_id", "installation-1"),
                                         "installation_id")
    plan = registry.install_plan(
        installation_id,
        _decode_requirements(request.get("requirements", ())),
    )
    if plan.resolution.conflicts:
        raise KernelError(
            code="DEPENDENCY_CONFLICT",
            message=(
                f"install plan for {installation_id} has "
                f"{len(plan.resolution.conflicts)} unresolvable constraint set(s)"
            ),
            retryable=False,
            recommended_action="change one of the two reported constraints; do not guess",
            details={"conflicts": [dict(item) for item in plan.resolution.conflicts]},
        )

    return {
        "registry_entry": entry.to_payload(),
        "registered_package": entry.to_payload(),
        "component_catalog": [dict(item) for item in registry.component_catalogue()],
        "install_plan": plan.to_payload(),
        "upgrade_plan": {
            "toReplace": [[name, before, after] for name, before, after in plan.to_replace],
            "blocked": [dict(item) for item in plan.blocked],
        },
        "permission_review": review_permissions(package).to_payload(),
        "promotion_decision": None if promotion is None else promotion.to_payload(),
        "revocation": None if revocation is None else revocation.to_payload(),
        "requires_action": [list(row) for row in registry.requires_action()],
    }
