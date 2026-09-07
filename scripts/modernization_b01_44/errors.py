#!/usr/bin/env python3
"""Typed refusals.

Every refusal carries a machine readable ``code`` so tests assert on the reason
rather than on prose, and so an audit record can be emitted without parsing
English.
"""

from __future__ import annotations

from typing import Any


class RuntimeRefusal(Exception):
    """Base class for every deliberate refusal in the B01-44 runtime."""

    code = "refused"

    def __init__(self, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def as_record(self) -> dict[str, Any]:
        record = {"code": self.code, "message": self.message}
        if self.detail:
            record["detail"] = self.detail
        return record


class PackageError(RuntimeRefusal):
    code = "package-invalid"


class SchemaViolation(RuntimeRefusal):
    code = "schema-violation"


class TrustBoundaryViolation(RuntimeRefusal):
    code = "trust-boundary-violation"


class PolicyViolation(RuntimeRefusal):
    code = "policy-violation"


class TenantIsolationViolation(PolicyViolation):
    code = "tenant-isolation-violation"


class AgentBoundaryViolation(PolicyViolation):
    code = "agent-boundary-violation"


class ApprovalRequired(RuntimeRefusal):
    code = "approval-required"


class EvidenceMissing(RuntimeRefusal):
    code = "evidence-missing"


class EvidenceExpired(RuntimeRefusal):
    code = "evidence-expired"


class CertificationBlocked(RuntimeRefusal):
    code = "certification-blocked"


class UpstreamCertificateMissing(CertificationBlocked):
    code = "upstream-certificate-missing"


class DeterminismViolation(RuntimeRefusal):
    code = "determinism-violation"


class WorkflowError(RuntimeRefusal):
    code = "workflow-error"


class LeaseExpired(WorkflowError):
    code = "lease-expired"


class BudgetExceeded(RuntimeRefusal):
    code = "budget-exceeded"


class ProviderDrift(RuntimeRefusal):
    code = "provider-drift"
