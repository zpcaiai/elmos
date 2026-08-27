"""Typed failures used at trust and recovery boundaries."""


class OpenHandsRuntimeError(Exception):
    """Base error with a stable machine-readable code."""

    code = "OPENHANDS_RUNTIME_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class ContractViolation(OpenHandsRuntimeError):
    code = "CONTRACT_VIOLATION"


class TenantIsolationError(OpenHandsRuntimeError):
    code = "TENANT_ISOLATION_VIOLATION"


class LeaseLost(OpenHandsRuntimeError):
    code = "LEASE_LOST"


class IdempotencyConflict(OpenHandsRuntimeError):
    code = "IDEMPOTENCY_CONFLICT"


class PolicyDenied(OpenHandsRuntimeError):
    code = "POLICY_DENIED"


class ApprovalRequired(OpenHandsRuntimeError):
    code = "APPROVAL_REQUIRED"


class BudgetExceeded(OpenHandsRuntimeError):
    code = "BUDGET_EXCEEDED"


class CorruptState(OpenHandsRuntimeError):
    code = "CORRUPT_STATE"


class NotConfigured(OpenHandsRuntimeError):
    code = "NOT_CONFIGURED"


class UnsupportedOperation(OpenHandsRuntimeError):
    code = "UNSUPPORTED_OPERATION"
