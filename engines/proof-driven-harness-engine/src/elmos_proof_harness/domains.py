"""Five exact domain-pack orchestration contracts with fail-closed proof gates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence


KERNEL_SEQUENCE = (
    "elmos-goal-specification-kernel",
    "elmos-repository-intelligence-kernel",
    "elmos-repository-semantic-compiler-kernel",
    "elmos-agentic-reasoning-kernel",
    "elmos-transformation-kernel",
    "elmos-proof-verification-kernel",
    "elmos-harness-runtime-kernel",
    "elmos-certification-kernel",
)


@dataclass(frozen=True, slots=True)
class ProofRequirement:
    template_id: str
    family: str
    severity: str
    required_evidence: tuple[str, ...] = ("static-or-formal", "differential-or-property")
    unknown_policy: str = "BLOCK"
    waiver_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "family": self.family,
            "severity": self.severity,
            "required_evidence": list(self.required_evidence),
            "unknown_policy": self.unknown_policy,
            "waiver_allowed": self.waiver_allowed,
        }


@dataclass(frozen=True, slots=True)
class DomainPack:
    name: str
    business_line: str
    scope: str
    source_profiles: tuple[str, ...]
    target_profiles: tuple[str, ...]
    proof_requirements: tuple[ProofRequirement, ...]
    minimum_certification: tuple[str, ...]
    version: str = "3.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "business_line": self.business_line,
            "scope": self.scope,
            "version": self.version,
            "source_profiles": list(self.source_profiles),
            "target_profiles": list(self.target_profiles),
            "kernel_sequence": list(KERNEL_SEQUENCE),
            "proof_requirements": [item.to_dict() for item in self.proof_requirements],
            "minimum_certification": list(self.minimum_certification),
            "legacy_skills_may_route": True,
            "independent_runtime": False,
        }


def _requirements(prefix: str, families: Sequence[str], critical_count: int) -> tuple[ProofRequirement, ...]:
    return tuple(
        ProofRequirement(
            f"{prefix}_PO_{index:03d}",
            family,
            "critical" if index <= critical_count else "high",
            unknown_policy="BLOCK" if index <= critical_count else "REVIEW",
            waiver_allowed=index > critical_count,
        )
        for index, family in enumerate(families, 1)
    )


DOMAIN_PACKS: dict[str, DomainPack] = {
    "cross-language-conversion": DomainPack(
        "cross-language-conversion",
        "cross-language",
        "Repository-scale cross-language and framework conversion across registered language profiles.",
        ("all registered language profiles",),
        ("all certified target profiles",),
        _requirements(
            "CROSS_LANGUAGE",
            (
                "types/nullability",
                "integer overflow and numeric precision",
                "Unicode/string/regex",
                "floating point and decimal",
                "time/date/timezone",
                "exceptions/effects/resources",
                "concurrency/async/memory model",
                "reflection/dynamic/FFI/ABI",
                "serialization/API/protocol",
                "data/transaction/cache/event state",
                "build/deploy/observability",
                "repository assume-guarantee composition",
            ),
            6,
        ),
        (
            "semantic profiles pinned",
            "product-program or translation validation for critical units",
            "behavioral differential coverage",
            "open-world boundaries monitored",
            "performance and resource budget accepted",
        ),
    ),
    "multi-language-project-generation": DomainPack(
        "multi-language-project-generation",
        "project-generation",
        "Generate a complete deployable and operable multi-language project from governed requirements and contracts.",
        ("Requirement Graph", "Data/API/Workflow/Security/Resource Formal Specs", "Architecture constraints"),
        ("backend/frontend/mobile/miniapp/data/AI/industrial system archetypes",),
        _requirements(
            "PROJECT_GENERATION",
            (
                "requirement satisfaction",
                "architecture constraint conformance",
                "API/schema invariants",
                "workflow safety/liveness/fairness",
                "tenant noninterference",
                "security and privacy",
                "resource/token/credit bounds",
                "build/deploy/ops completeness",
                "UI/accessibility/compatibility",
                "observability/rollback/disaster recovery",
            ),
            5,
        ),
        (
            "requirements traceability 100% for critical requirements",
            "architecture decisions recorded",
            "generated core verified or rigorously tested",
            "deployability P05",
            "customer acceptance scenarios pass",
        ),
    ),
    "repository-refactoring": DomainPack(
        "repository-refactoring",
        "repository-refactoring",
        "Cross-file, module, and service refactoring with explicit architecture, API, concurrency, performance, and security contracts.",
        ("existing repository semantic profile",),
        ("approved architecture and quality target",),
        _requirements(
            "REPOSITORY_REFACTORING",
            (
                "observable behavior preservation",
                "public contract compatibility",
                "data and event invariants",
                "architecture constraints",
                "dependency and supply-chain safety",
                "performance/resource guardrails",
                "concurrency correctness",
                "operational continuity",
                "rollback and staged rollout",
            ),
            4,
        ),
        (
            "public contract unchanged or versioned",
            "critical behavior preserved",
            "architecture constraints pass",
            "mutation effectiveness",
            "canary/rollback readiness",
        ),
    ),
    "spring-legacy-modernization": DomainPack(
        "spring-legacy-modernization",
        "spring-modernization",
        "Semantics-preserving Struts, Servlet, JSP, and mixed legacy Java web modernization to Spring Boot 4.",
        ("Struts 1", "Struts 2", "Servlet/JSP", "Spring Framework legacy", "EJB/JPA/Hibernate legacy", "XML-heavy configuration"),
        ("Spring Boot 4", "Spring Framework 7", "Jakarta EE namespace", "Spring Security 7", "supported Java LTS profile"),
        _requirements(
            "SPRING_MODERNIZATION",
            (
                "route precedence and method equivalence",
                "request binding/validation",
                "session state refinement",
                "filter/interceptor/AOP ordering",
                "authentication/authorization dominance",
                "exception/status/view refinement",
                "transaction boundary and rollback",
                "ORM/schema/data migration",
                "JSP/view observable output",
                "async/scheduling/messaging",
                "external side effects",
                "performance/security/supply chain",
            ),
            6,
        ),
        (
            "baseline reproducible",
            "critical route coverage 100%",
            "security dominance preserved",
            "no unresolved P0 semantic gap",
            "dual-runtime differential within contract",
            "rollback rehearsed",
        ),
    ),
    "sql-dialect-routine-conversion": DomainPack(
        "sql-dialect-routine-conversion",
        "sql-conversion",
        "Exact SQL dialect, schema, query, routine, trigger, and transaction conversion between named database engines.",
        ("PostgreSQL", "Oracle", "SQL Server", "MySQL/MariaDB", "DB2", "Snowflake", "BigQuery", "Redshift", "Teradata", "SQLite", "Hive/Spark SQL"),
        ("registered SQL/runtime profiles",),
        _requirements(
            "SQL_CONVERSION",
            (
                "bag/set/order semantics",
                "NULL and three-valued logic",
                "type/precision/collation/time",
                "query equivalence",
                "lossless schema mapping",
                "constraint preservation",
                "DML state equivalence",
                "routine CFG/SSA contracts",
                "trigger trace and termination",
                "dynamic SQL boundary",
                "transaction/isolation/exception",
                "query plan/performance",
            ),
            6,
        ),
        (
            "schema losslessness closed",
            "critical query/routine equivalence",
            "transaction semantics accepted",
            "data reconciliation zero unexplained drift",
            "performance regression within contract",
        ),
    ),
}


@dataclass(frozen=True, slots=True)
class DomainExecutionPlan:
    plan_id: str
    pack: DomainPack
    input_digest: str
    kernel_sequence: tuple[str, ...]
    obligations: tuple[ProofRequirement, ...]
    state: str = "PLANNED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "pack": self.pack.name,
            "pack_version": self.pack.version,
            "input_digest": self.input_digest,
            "kernel_sequence": list(self.kernel_sequence),
            "obligations": [item.to_dict() for item in self.obligations],
            "state": self.state,
            "certified": False,
        }


@dataclass(frozen=True, slots=True)
class DomainGateDecision:
    pack: str
    decision: str
    passed: tuple[str, ...]
    blocked: tuple[str, ...]
    review: tuple[str, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack": self.pack,
            "decision": self.decision,
            "passed": list(self.passed),
            "blocked": list(self.blocked),
            "review": list(self.review),
            "reasons": list(self.reasons),
            "certified": False,
        }


class DomainPackOrchestrator:
    def __init__(self, packs: Mapping[str, DomainPack] | None = None) -> None:
        self.packs = dict(packs or DOMAIN_PACKS)

    def plan(self, pack_name: str, inputs: Mapping[str, Any]) -> DomainExecutionPlan:
        pack = self.packs.get(pack_name)
        if pack is None:
            raise KeyError(f"unknown domain pack: {pack_name}")
        if not isinstance(inputs, Mapping) or not inputs:
            raise ValueError("domain pack inputs must be a non-empty object")
        input_digest = _digest(inputs)
        plan_id = f"domain-plan:sha256:{_digest([pack.name, pack.version, input_digest, KERNEL_SEQUENCE])}"
        return DomainExecutionPlan(plan_id, pack, input_digest, KERNEL_SEQUENCE, pack.proof_requirements)

    def evaluate(
        self,
        pack_name: str,
        evidence_by_obligation: Mapping[str, Sequence[Mapping[str, Any]]],
        *,
        durable_verified_evidence: Mapping[str, Sequence[str]] | None = None,
    ) -> DomainGateDecision:
        pack = self.packs.get(pack_name)
        if pack is None:
            raise KeyError(f"unknown domain pack: {pack_name}")
        passed: list[str] = []
        blocked: list[str] = []
        review: list[str] = []
        reasons: list[str] = []
        verified = {
            obligation_id: set(kinds)
            for obligation_id, kinds in (durable_verified_evidence or {}).items()
        }
        for obligation in pack.proof_requirements:
            records = evidence_by_obligation.get(obligation.template_id, ())
            # Payload records are syntax-only claims.  Only the durable control
            # plane may supply kinds obtained after EvidenceService re-read and
            # verification of stored bytes.
            valid_kinds = verified.get(obligation.template_id, set())
            invalid = bool(records) and durable_verified_evidence is None
            missing = set(obligation.required_evidence) - valid_kinds
            if not missing and not invalid:
                passed.append(obligation.template_id)
            elif obligation.unknown_policy == "BLOCK":
                blocked.append(obligation.template_id)
                reasons.append(
                    f"{obligation.template_id} missing durable byte-verified evidence: {sorted(missing)}"
                )
            else:
                review.append(obligation.template_id)
                reasons.append(
                    f"{obligation.template_id} requires review: missing {sorted(missing)}"
                )
        if blocked:
            decision = "BLOCKED"
        elif review:
            decision = "READY_FOR_HUMAN_DECISION"
        elif len(passed) == len(pack.proof_requirements):
            decision = "READY_FOR_EXTERNAL_GATE"
        else:
            decision = "INCONCLUSIVE"
        return DomainGateDecision(pack.name, decision, tuple(passed), tuple(blocked), tuple(review), tuple(reasons))


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "DOMAIN_PACKS",
    "DomainExecutionPlan",
    "DomainGateDecision",
    "DomainPack",
    "DomainPackOrchestrator",
    "KERNEL_SEQUENCE",
    "ProofRequirement",
]
