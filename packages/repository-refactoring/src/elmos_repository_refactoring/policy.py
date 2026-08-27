"""``RefactorPolicy`` — the operator-owned rules a run is evaluated against.

A policy is *not* part of the task payload.  It arrives through the trusted
context, is digest-bound into every approval and evidence bundle, and is the
only place that can widen autonomy, relax a gate or permit network access.

When no policy is supplied the package uses :data:`ENTERPRISE_DEFAULT_POLICY`,
which is deliberately the most restrictive configuration that still lets an
analysis run complete: deny-all network, no autonomy above R1, every structural
gate blocking.  "No policy" must never mean "no rules".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from .contracts import (
    AdapterLevel,
    ContractError,
    ExecutionMode,
    GateOutcome,
    NetworkPolicy,
    RiskClass,
    decimal_value,
    integer_value,
    optional_bool,
    optional_string,
    reject_unknown_fields,
    require_bool,
    require_enum,
    require_mapping,
    require_mapping_sequence,
    require_string,
    require_string_sequence,
    sha256_payload,
)
from .expressions import UNKNOWN, compile_expression

POLICY_KIND = "RefactorPolicy"
API_VERSION = "elmos.dev/v1"


@dataclass(frozen=True, slots=True)
class ApprovalRule:
    when: str
    roles: tuple[str, ...]
    minimum_approvers: int = 1

    def matches(self, context: Mapping[str, Any]) -> bool | None:
        result = compile_expression(self.when).evaluate(context)
        return None if result is UNKNOWN else bool(result)

    def to_payload(self) -> dict[str, Any]:
        return {"when": self.when, "roles": list(self.roles), "minimumApprovers": self.minimum_approvers}

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> ApprovalRule:
        reject_unknown_fields(value, {"when", "roles", "minimumApprovers"}, "spec.approvals[]")
        when = require_string(value.get("when"), "spec.approvals[].when", max_length=4096)
        compile_expression(when)  # fail closed at load time, not at gate time
        return cls(
            when=when,
            roles=require_string_sequence(value.get("roles"), "spec.approvals[].roles", allow_empty=False, unique=True),
            minimum_approvers=integer_value(
                value.get("minimumApprovers", 1), "spec.approvals[].minimumApprovers", minimum=1, maximum=16
            ),
        )


@dataclass(frozen=True, slots=True)
class QualityGateRule:
    gate: str
    blocking: bool
    when: str | None = None

    def applies(self, context: Mapping[str, Any]) -> bool | None:
        if self.when is None:
            return True
        result = compile_expression(self.when).evaluate(context)
        return None if result is UNKNOWN else bool(result)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"gate": self.gate, "blocking": self.blocking}
        if self.when:
            payload["when"] = self.when
        return payload

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> QualityGateRule:
        reject_unknown_fields(value, {"gate", "blocking", "when"}, "spec.qualityGates[]")
        when = optional_string(value.get("when"), "spec.qualityGates[].when", max_length=4096)
        if when is not None:
            compile_expression(when)
        return cls(
            gate=require_string(value.get("gate"), "spec.qualityGates[].gate", max_length=128),
            blocking=require_bool(value.get("blocking"), "spec.qualityGates[].blocking"),
            when=when,
        )


@dataclass(frozen=True, slots=True)
class AutonomyPolicy:
    max_risk_class: RiskClass = RiskClass.R1
    minimum_adapter_level: AdapterLevel = AdapterLevel.L4
    minimum_verification_score: Decimal = Decimal("0.95")

    def to_payload(self) -> dict[str, Any]:
        return {
            "maxRiskClass": self.max_risk_class.value,
            "minimumAdapterLevel": self.minimum_adapter_level.value,
            "minimumVerificationScore": str(self.minimum_verification_score),
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> AutonomyPolicy:
        if value is None:
            return cls()
        mapping = require_mapping(value, "spec.autonomy")
        reject_unknown_fields(
            mapping, {"maxRiskClass", "minimumAdapterLevel", "minimumVerificationScore"}, "spec.autonomy"
        )
        return cls(
            max_risk_class=require_enum(mapping.get("maxRiskClass", "R1"), RiskClass, "spec.autonomy.maxRiskClass"),
            minimum_adapter_level=require_enum(
                mapping.get("minimumAdapterLevel", "L4"), AdapterLevel, "spec.autonomy.minimumAdapterLevel"
            ),
            minimum_verification_score=decimal_value(
                mapping.get("minimumVerificationScore", "0.95"),
                "spec.autonomy.minimumVerificationScore",
                minimum=Decimal("0"),
                maximum=Decimal("1"),
            ),
        )


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    network: NetworkPolicy = NetworkPolicy.DENY
    max_cpu: Decimal = Decimal("4")
    max_memory_mib: int = 8192
    max_disk_mib: int = 40960
    max_processes: int = 256

    def to_payload(self) -> dict[str, Any]:
        return {
            "network": self.network.value,
            "maxCpu": str(self.max_cpu),
            "maxMemoryMiB": self.max_memory_mib,
            "maxDiskMiB": self.max_disk_mib,
            "maxProcesses": self.max_processes,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> SandboxPolicy:
        if value is None:
            return cls()
        mapping = require_mapping(value, "spec.sandbox")
        reject_unknown_fields(
            mapping, {"network", "maxCpu", "maxMemoryMiB", "maxDiskMiB", "maxProcesses"}, "spec.sandbox"
        )
        return cls(
            network=require_enum(mapping.get("network", "deny"), NetworkPolicy, "spec.sandbox.network"),
            max_cpu=decimal_value(mapping.get("maxCpu", 4), "spec.sandbox.maxCpu", minimum=Decimal("0.1")),
            max_memory_mib=integer_value(mapping.get("maxMemoryMiB", 8192), "spec.sandbox.maxMemoryMiB", minimum=64),
            max_disk_mib=integer_value(mapping.get("maxDiskMiB", 40960), "spec.sandbox.maxDiskMiB", minimum=64),
            max_processes=integer_value(mapping.get("maxProcesses", 256), "spec.sandbox.maxProcesses", minimum=1),
        )


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    evidence_days: int = 365
    patch_days: int = 365
    log_days: int = 90
    redact_source_content: bool = True

    def to_payload(self) -> dict[str, Any]:
        return {
            "evidenceDays": self.evidence_days,
            "patchDays": self.patch_days,
            "logDays": self.log_days,
            "redactSourceContent": self.redact_source_content,
        }

    @classmethod
    def from_payload(cls, value: Mapping[str, Any] | None) -> RetentionPolicy:
        if value is None:
            return cls()
        mapping = require_mapping(value, "spec.retention")
        reject_unknown_fields(
            mapping, {"evidenceDays", "patchDays", "logDays", "redactSourceContent"}, "spec.retention"
        )
        return cls(
            evidence_days=integer_value(mapping.get("evidenceDays", 365), "spec.retention.evidenceDays", minimum=1),
            patch_days=integer_value(mapping.get("patchDays", 365), "spec.retention.patchDays", minimum=1),
            log_days=integer_value(mapping.get("logDays", 90), "spec.retention.logDays", minimum=1),
            redact_source_content=optional_bool(
                mapping.get("redactSourceContent"), "spec.retention.redactSourceContent", True
            ),
        )


@dataclass(frozen=True, slots=True)
class RefactorPolicy:
    name: str
    version: str
    owner: str | None
    allowed_modes: tuple[ExecutionMode, ...]
    autonomy: AutonomyPolicy
    approvals: tuple[ApprovalRule, ...]
    sandbox: SandboxPolicy
    quality_gates: tuple[QualityGateRule, ...]
    forbidden_patterns: tuple[str, ...]
    retention: RetentionPolicy

    # -- derived ---------------------------------------------------------

    def to_payload(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {"name": self.name, "version": self.version}
        if self.owner:
            metadata["owner"] = self.owner
        return {
            "apiVersion": API_VERSION,
            "kind": POLICY_KIND,
            "metadata": metadata,
            "spec": {
                "allowedModes": [mode.value for mode in self.allowed_modes],
                "autonomy": self.autonomy.to_payload(),
                "approvals": [rule.to_payload() for rule in self.approvals],
                "sandbox": self.sandbox.to_payload(),
                "qualityGates": [rule.to_payload() for rule in self.quality_gates],
                "forbiddenPatterns": list(self.forbidden_patterns),
                "retention": self.retention.to_payload(),
            },
        }

    @property
    def digest(self) -> str:
        return sha256_payload(self.to_payload())

    @property
    def blocking_gates(self) -> tuple[str, ...]:
        return tuple(sorted({rule.gate for rule in self.quality_gates if rule.blocking}))

    def gate_rule(self, gate: str) -> QualityGateRule | None:
        for rule in self.quality_gates:
            if rule.gate == gate:
                return rule
        return None

    def permits_mode(self, mode: ExecutionMode) -> bool:
        return mode in self.allowed_modes

    def required_approval_roles(self, context: Mapping[str, Any]) -> tuple[tuple[str, ...], ...]:
        """Role sets that must sign off for ``context``.

        A rule whose ``when`` cannot be decided counts as *matching*: an
        undecidable approval condition escalates, it never waives.
        """

        required: list[tuple[str, ...]] = []
        for rule in self.approvals:
            verdict = rule.matches(context)
            if verdict is None or verdict:
                required.append(rule.roles)
        return tuple(required)

    def forbids(self, path: str) -> str | None:
        from .contracts import match_path_glob

        for pattern in self.forbidden_patterns:
            if match_path_glob(path, pattern):
                return pattern
        return None

    def gate_outcome(self, gate: str, passed: bool | None, context: Mapping[str, Any]) -> GateOutcome:
        """Map a raw gate result onto a policy-aware outcome."""

        rule = self.gate_rule(gate)
        if rule is None:
            return GateOutcome.NOT_APPLICABLE if passed is None else (
                GateOutcome.PASS if passed else GateOutcome.FAIL
            )
        applies = rule.applies(context)
        if applies is False:
            return GateOutcome.NOT_APPLICABLE
        if passed is None:
            # Undecided under a blocking rule is a failure, never a pass.
            return GateOutcome.FAIL if rule.blocking or applies is None else GateOutcome.NOT_APPLICABLE
        return GateOutcome.PASS if passed else GateOutcome.FAIL

    # -- parsing ---------------------------------------------------------

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> RefactorPolicy:
        value = require_mapping(payload, "policy")
        reject_unknown_fields(value, {"apiVersion", "kind", "metadata", "spec"}, "policy")
        if value.get("apiVersion") != API_VERSION:
            raise ContractError("invalid_api_version", f"policy.apiVersion must be {API_VERSION}")
        if value.get("kind") != POLICY_KIND:
            raise ContractError("invalid_kind", f"policy.kind must be {POLICY_KIND}")
        metadata = require_mapping(value.get("metadata"), "policy.metadata")
        reject_unknown_fields(metadata, {"name", "version", "digest", "owner"}, "policy.metadata")
        spec = require_mapping(value.get("spec"), "policy.spec")
        reject_unknown_fields(
            spec,
            {
                "allowedModes",
                "autonomy",
                "approvals",
                "sandbox",
                "qualityGates",
                "forbiddenPatterns",
                "retention",
            },
            "policy.spec",
        )
        modes_raw = require_string_sequence(
            spec.get("allowedModes", [mode.value for mode in ExecutionMode]),
            "policy.spec.allowedModes",
            allow_empty=False,
            unique=True,
        )
        modes = tuple(require_enum(item, ExecutionMode, "policy.spec.allowedModes[]") for item in modes_raw)
        gates = tuple(
            QualityGateRule.from_payload(item)
            for item in require_mapping_sequence(spec.get("qualityGates", ()), "policy.spec.qualityGates")
        )
        gate_names = [rule.gate for rule in gates]
        if len(set(gate_names)) != len(gate_names):
            raise ContractError("duplicate_gate", "policy.spec.qualityGates contains duplicate gate names")
        policy = cls(
            name=require_string(metadata.get("name"), "policy.metadata.name", max_length=128),
            version=require_string(metadata.get("version"), "policy.metadata.version", max_length=64),
            owner=optional_string(metadata.get("owner"), "policy.metadata.owner"),
            allowed_modes=modes,
            autonomy=AutonomyPolicy.from_payload(spec.get("autonomy")),
            approvals=tuple(
                ApprovalRule.from_payload(item)
                for item in require_mapping_sequence(spec.get("approvals", ()), "policy.spec.approvals")
            ),
            sandbox=SandboxPolicy.from_payload(spec.get("sandbox")),
            quality_gates=gates,
            forbidden_patterns=require_string_sequence(
                spec.get("forbiddenPatterns", ()), "policy.spec.forbiddenPatterns", unique=True
            ),
            retention=RetentionPolicy.from_payload(spec.get("retention")),
        )
        declared = metadata.get("digest")
        if declared is not None and declared != policy.digest:
            raise ContractError(
                "policy_digest_mismatch",
                "policy.metadata.digest does not match the canonical policy content",
            )
        return policy


#: Structural gates that always exist.  A policy may make one non-blocking, but
#: it cannot make one disappear: the verifier still reports every entry.
BASELINE_GATES: tuple[tuple[str, bool, str | None], ...] = (
    ("parse", True, None),
    ("round-trip", True, None),
    ("idempotence", True, None),
    ("scope-containment", True, None),
    ("anti-cheat", True, None),
    ("typecheck", True, None),
    ("build", True, None),
    ("changed-target-tests", True, None),
    ("full-tests", True, "risk.class in ['R3','R4','R5']"),
    ("api-compatibility", True, "impact.public_api_touched"),
    ("schema-compatibility", True, "impact.database_touched"),
    ("security-scan", True, "risk.class in ['R3','R4','R5'] or impact.security_touched"),
    ("license-scan", False, None),
    ("performance", True, "risk.class in ['R3','R4','R5'] and impact.performance_sensitive"),
    ("rollback-proof", True, "execution.mutates"),
    ("evidence-completeness", True, None),
)


def _default_policy_payload() -> dict[str, Any]:
    return {
        "apiVersion": API_VERSION,
        "kind": POLICY_KIND,
        "metadata": {"name": "enterprise-default", "version": "1.0.0", "owner": "elmos-refactoring-platform"},
        "spec": {
            "allowedModes": ["analyze-only", "proposal", "supervised", "fleet-wave"],
            "autonomy": {
                "maxRiskClass": "R1",
                "minimumAdapterLevel": "L4",
                "minimumVerificationScore": "0.95",
            },
            "approvals": [
                {"when": "risk.class in ['R3','R4','R5']", "roles": ["tech-lead"], "minimumApprovers": 1},
                {
                    "when": "impact.database_touched or impact.security_touched",
                    "roles": ["tech-lead", "security-owner"],
                    "minimumApprovers": 2,
                },
                {"when": "impact.public_api_breaking", "roles": ["api-owner"], "minimumApprovers": 1},
                {"when": "scope.expanded", "roles": ["tech-lead"], "minimumApprovers": 1},
            ],
            "sandbox": {
                "network": "deny",
                "maxCpu": "4",
                "maxMemoryMiB": 8192,
                "maxDiskMiB": 40960,
                "maxProcesses": 256,
            },
            "qualityGates": [
                {"gate": gate, "blocking": blocking, **({"when": when} if when else {})}
                for gate, blocking, when in BASELINE_GATES
            ],
            "forbiddenPatterns": [
                "**/.git/**",
                "**/*.pem",
                "**/*.p12",
                "**/*.keystore",
                "**/id_rsa*",
                "**/.env",
                "**/.env.*",
                "**/secrets/**",
            ],
            "retention": {"evidenceDays": 365, "patchDays": 365, "logDays": 90, "redactSourceContent": True},
        },
    }


ENTERPRISE_DEFAULT_POLICY: RefactorPolicy = RefactorPolicy.from_payload(_default_policy_payload())

BUILTIN_POLICIES: Mapping[str, RefactorPolicy] = MappingProxyType(
    {ENTERPRISE_DEFAULT_POLICY.name: ENTERPRISE_DEFAULT_POLICY}
)


def resolve_policy(payload: Mapping[str, Any] | None, *, reference: str | None = None) -> RefactorPolicy:
    """Resolve an explicit policy document, a builtin name, or the default."""

    if payload is not None:
        return RefactorPolicy.from_payload(payload)
    if reference is None:
        return ENTERPRISE_DEFAULT_POLICY
    policy = BUILTIN_POLICIES.get(reference)
    if policy is None:
        raise ContractError(
            "unknown_policy",
            f"policy reference '{reference}' is not resolvable in this runtime",
            {"known": sorted(BUILTIN_POLICIES)},
        )
    return policy


def evaluate_gate_set(
    policy: RefactorPolicy,
    results: Mapping[str, bool | None],
    context: Mapping[str, Any],
) -> tuple[dict[str, GateOutcome], tuple[str, ...]]:
    """Return every gate's outcome plus the blocking failures.

    Gates declared by the policy but absent from ``results`` are *not* ignored:
    an applicable gate with no result is undecided, and an undecided blocking
    gate fails.  This is what stops "we did not run it" from scoring as "it
    passed".
    """

    outcomes: dict[str, GateOutcome] = {}
    for rule in policy.quality_gates:
        outcomes[rule.gate] = policy.gate_outcome(rule.gate, results.get(rule.gate), context)
    for gate, passed in results.items():
        if gate not in outcomes:
            outcomes[gate] = policy.gate_outcome(gate, passed, context)
    blocking_failures = tuple(
        sorted(
            gate
            for gate, outcome in outcomes.items()
            if outcome is GateOutcome.FAIL and (policy.gate_rule(gate) is None or policy.gate_rule(gate).blocking)  # type: ignore[union-attr]
        )
    )
    return outcomes, blocking_failures


def sandbox_permits(policy: RefactorPolicy, requested: NetworkPolicy) -> bool:
    order: Sequence[NetworkPolicy] = (NetworkPolicy.DENY, NetworkPolicy.RESTORE_ONLY, NetworkPolicy.ALLOWLISTED)
    return order.index(requested) <= order.index(policy.sandbox.network)


__all__ = [
    "BASELINE_GATES",
    "BUILTIN_POLICIES",
    "ENTERPRISE_DEFAULT_POLICY",
    "ApprovalRule",
    "AutonomyPolicy",
    "QualityGateRule",
    "RefactorPolicy",
    "RetentionPolicy",
    "SandboxPolicy",
    "evaluate_gate_set",
    "resolve_policy",
    "sandbox_permits",
]
