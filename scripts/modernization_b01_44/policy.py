#!/usr/bin/env python3
"""Policy enforcement: default-deny, tenant isolation and the Agent boundary.

The rules are not hard-coded here.  They are read from the Batch package's own
``policies/*.yaml`` files, so a package that relaxes a policy immediately
changes runtime behaviour and the corresponding test fails.  That is the point:
the policy files are executable, not decorative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scripts.modernization_b01_44.canonical import digest
from scripts.modernization_b01_44.errors import (
    AgentBoundaryViolation,
    PolicyViolation,
    TenantIsolationViolation,
    TrustBoundaryViolation,
)
from scripts.modernization_b01_44.packages import BatchPackage

#: Capabilities that ``default-deny.yaml`` can gate.
GATED_CAPABILITIES = ("network", "host_filesystem", "production_secrets", "arbitrary_shell")

#: Artefact classes an Agent may never write, regardless of proposal quality.
AGENT_PROTECTED_ARTEFACTS = {
    "tests": "modify_tests",
    "golden": "modify_golden",
    "gate": "modify_gate",
    "certificate": "modify_gate",
    "policy": "modify_gate",
}


@dataclass(frozen=True)
class Principal:
    """Who is asking.  ``kind`` decides which boundary applies."""

    principal_id: str
    tenant_id: str
    kind: str = "human"  # human | service | agent
    roles: frozenset[str] = field(default_factory=frozenset)

    @property
    def is_agent(self) -> bool:
        return self.kind == "agent"


@dataclass
class AuditRecord:
    decision: str
    reason: str
    principal_id: str
    tenant_id: str
    resource: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "principal_id": self.principal_id,
            "tenant_id": self.tenant_id,
            "resource": self.resource,
            "detail": self.detail,
        }


class PolicyEngine:
    """Evaluate a Batch package's policies against concrete requests."""

    def __init__(self, package: BatchPackage) -> None:
        self.package = package
        self._default_deny = package.policy("default-deny").get("default_deny", {})
        self._agent_boundary = package.policy("agent-boundary").get("agent_boundary", {})
        self._evidence_first = package.policy("evidence-first").get("evidence_first", {})
        self._human_approval = package.policy("human-approval").get("human_approval", {})
        self._certification = package.policy("certification").get("certification", {})
        self.audit_log: list[AuditRecord] = []

    # -- introspection ---------------------------------------------------

    @property
    def evidence_first(self) -> dict[str, Any]:
        return dict(self._evidence_first)

    @property
    def certification_policy(self) -> dict[str, Any]:
        return dict(self._certification)

    @property
    def approval_policy(self) -> dict[str, Any]:
        return dict(self._human_approval)

    def denies(self, capability: str) -> bool:
        if capability not in GATED_CAPABILITIES:
            raise PolicyViolation("unknown capability", capability=capability)
        return bool(self._default_deny.get(capability, True))

    # -- enforcement -----------------------------------------------------

    def _audit(self, decision: str, reason: str, principal: Principal, resource: str, **detail: Any) -> AuditRecord:
        record = AuditRecord(
            decision=decision,
            reason=reason,
            principal_id=principal.principal_id,
            tenant_id=principal.tenant_id,
            resource=resource,
            detail=detail,
        )
        self.audit_log.append(record)
        return record

    def check_capability(self, principal: Principal, capability: str, *, grant: bool = False) -> None:
        """Default deny: a gated capability needs an explicit, audited grant."""

        if self.denies(capability) and not grant:
            self._audit("deny", "default-deny", principal, capability)
            raise PolicyViolation(
                "capability is denied by default and no explicit grant was presented",
                capability=capability,
            )
        self._audit("allow", "explicit-grant" if grant else "not-gated", principal, capability)

    def check_tenant(self, principal: Principal, resource_tenant_id: str, resource: str) -> None:
        """Refuse and audit any cross-tenant reach."""

        if principal.tenant_id != resource_tenant_id:
            self._audit(
                "deny",
                "cross-tenant",
                principal,
                resource,
                resource_tenant_digest=digest(resource_tenant_id),
            )
            raise TenantIsolationViolation(
                "principal tenant does not own the requested resource",
                resource=resource,
                principal_tenant_digest=digest(principal.tenant_id),
                resource_tenant_digest=digest(resource_tenant_id),
            )
        self._audit("allow", "same-tenant", principal, resource)

    def check_agent_write(self, principal: Principal, artefact_class: str, *, mode: str = "commit") -> None:
        """Enforce ``agent-boundary.yaml``.

        Agents may *propose*.  They may not commit, self-approve, or touch
        tests, golden data, gates, certificates or policies by any route.
        """

        if not principal.is_agent:
            return
        if artefact_class in AGENT_PROTECTED_ARTEFACTS:
            flag = AGENT_PROTECTED_ARTEFACTS[artefact_class]
            if not self._agent_boundary.get(flag, False):
                self._audit("deny", f"agent-boundary:{flag}", principal, artefact_class)
                raise AgentBoundaryViolation(
                    "agents may not modify this artefact class",
                    artefact_class=artefact_class,
                    policy_flag=flag,
                )
        if mode == "commit" and not self._agent_boundary.get("direct_commit", False):
            self._audit("deny", "agent-boundary:direct_commit", principal, artefact_class)
            raise AgentBoundaryViolation(
                "agents are proposal-only and may not commit directly",
                artefact_class=artefact_class,
            )
        if mode == "approve" and not self._agent_boundary.get("self_approval", False):
            self._audit("deny", "agent-boundary:self_approval", principal, artefact_class)
            raise AgentBoundaryViolation("agents may not approve their own proposals")
        self._audit("allow", "agent-proposal", principal, artefact_class)

    def check_trust_boundary(self, payload: Any, schema: dict[str, Any], *, label: str = "input") -> None:
        """Reject anything the declared schema does not model."""

        from scripts.modernization_b01_44.validation import validate  # local: avoid cycle
        from scripts.modernization_b01_44.errors import SchemaViolation

        try:
            validate(payload, schema, label=label)
        except SchemaViolation as exc:
            raise TrustBoundaryViolation(
                "payload was refused at the trust boundary",
                label=label,
                reason=exc.message,
                **exc.detail,
            ) from exc
