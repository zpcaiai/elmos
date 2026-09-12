"""Error taxonomy and exception mapping for Elmos Router Industrial.

Maps all provider, gateway, and infrastructure errors into the stable 17-class taxonomy.
Resolves retryability and fallback eligibility based on error class, deadline, and policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ErrorTaxonomyClass(str, Enum):
    AUTH = "AUTH"
    PERMISSION = "PERMISSION"
    POLICY_DENIED = "POLICY_DENIED"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    PROVIDER_4XX = "PROVIDER_4XX"
    PROVIDER_5XX = "PROVIDER_5XX"
    CONTENT_REFUSAL = "CONTENT_REFUSAL"
    CONTEXT_OVERFLOW = "CONTEXT_OVERFLOW"
    INVALID_STRUCTURED_OUTPUT = "INVALID_STRUCTURED_OUTPUT"
    TOOL_PROTOCOL_ERROR = "TOOL_PROTOCOL_ERROR"
    NETWORK = "NETWORK"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    BUDGET_DENIED = "BUDGET_DENIED"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"


# Static taxonomy rules: (default_retryable, default_fallback_eligible)
_TAXONOMY_RULES: dict[ErrorTaxonomyClass, tuple[bool, bool]] = {
    ErrorTaxonomyClass.AUTH: (False, False),
    ErrorTaxonomyClass.PERMISSION: (False, False),
    ErrorTaxonomyClass.POLICY_DENIED: (False, False),
    ErrorTaxonomyClass.RATE_LIMIT: (True, True),
    ErrorTaxonomyClass.QUOTA_EXHAUSTED: (False, True),
    ErrorTaxonomyClass.TIMEOUT: (True, True),
    ErrorTaxonomyClass.CANCELLED: (False, False),
    ErrorTaxonomyClass.PROVIDER_4XX: (False, False),
    ErrorTaxonomyClass.PROVIDER_5XX: (True, True),
    ErrorTaxonomyClass.CONTENT_REFUSAL: (False, False),
    ErrorTaxonomyClass.CONTEXT_OVERFLOW: (False, True),
    ErrorTaxonomyClass.INVALID_STRUCTURED_OUTPUT: (True, True),
    ErrorTaxonomyClass.TOOL_PROTOCOL_ERROR: (False, True),
    ErrorTaxonomyClass.NETWORK: (True, True),
    ErrorTaxonomyClass.CIRCUIT_OPEN: (False, True),
    ErrorTaxonomyClass.BUDGET_DENIED: (False, False),
    ErrorTaxonomyClass.UNSUPPORTED_CAPABILITY: (False, True),
}


class RouterBaseError(Exception):
    """Base error for all Elmos Router Industrial exceptions."""
    def __init__(
        self,
        message: str,
        taxonomy_class: ErrorTaxonomyClass = ErrorTaxonomyClass.PROVIDER_4XX,
    ) -> None:
        super().__init__(f"[{taxonomy_class.value}] {message}")
        self.taxonomyClass = taxonomy_class
        self.message = message


@dataclass
class ProviderError(RouterBaseError):
    taxonomyClass: ErrorTaxonomyClass
    message: str
    statusCode: int | None = None
    providerId: str | None = None
    deploymentId: str | None = None
    rawErrorPayload: Mapping[str, Any] | None = None
    retryAfterSeconds: float | None = None
    retryable: bool = field(init=False)
    fallbackEligible: bool = field(init=False)

    def __post_init__(self) -> None:
        RouterBaseError.__init__(self, self.message, self.taxonomyClass)
        default_retry, default_fallback = _TAXONOMY_RULES.get(
            self.taxonomyClass, (False, False)
        )
        self.retryable = default_retry
        self.fallbackEligible = default_fallback


    def is_retryable(
        self,
        deadline: datetime | None = None,
        retries_remaining: int = 0,
        now: datetime | None = None,
    ) -> bool:
        if not self.retryable or retries_remaining <= 0:
            return False
        if deadline is not None:
            current_time = now or datetime.now(timezone.utc)
            if current_time >= deadline:
                return False
            if self.retryAfterSeconds and (
                current_time.timestamp() + self.retryAfterSeconds
                >= deadline.timestamp()
            ):
                return False
        return True

    def is_fallback_eligible(self) -> bool:
        return self.fallbackEligible


class PolicyViolationError(RouterBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorTaxonomyClass.POLICY_DENIED)


class ContractValidationError(RouterBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorTaxonomyClass.INVALID_STRUCTURED_OUTPUT)


class ConfigurationError(RouterBaseError):
    def __init__(self, message: str) -> None:
        super().__init__(message, ErrorTaxonomyClass.PROVIDER_4XX)



def map_http_status_to_taxonomy(
    status_code: int,
    error_body: Mapping[str, Any] | None = None,
    message: str | None = None,
) -> ErrorTaxonomyClass:
    """Classifies an HTTP status code and optional response body into ErrorTaxonomyClass."""
    body_str = str(error_body or {}).lower()
    msg = (message or "").lower()

    if status_code == 401:
        return ErrorTaxonomyClass.AUTH
    elif status_code == 403:
        if "policy" in body_str or "policy" in msg:
            return ErrorTaxonomyClass.POLICY_DENIED
        return ErrorTaxonomyClass.PERMISSION
    elif status_code == 429:
        if "quota" in body_str or "quota" in msg or "insufficient_quota" in body_str:
            return ErrorTaxonomyClass.QUOTA_EXHAUSTED
        return ErrorTaxonomyClass.RATE_LIMIT
    elif status_code == 408 or status_code == 504:
        return ErrorTaxonomyClass.TIMEOUT
    elif status_code == 400:
        if "context_length" in body_str or "context length" in msg or "maximum context" in body_str:
            return ErrorTaxonomyClass.CONTEXT_OVERFLOW
        if "content_filter" in body_str or "refusal" in msg or "safety" in body_str:
            return ErrorTaxonomyClass.CONTENT_REFUSAL
        if "tool" in body_str or "function_call" in body_str:
            return ErrorTaxonomyClass.TOOL_PROTOCOL_ERROR
        if "json" in body_str or "schema" in body_str or "structured" in msg:
            return ErrorTaxonomyClass.INVALID_STRUCTURED_OUTPUT
        return ErrorTaxonomyClass.PROVIDER_4XX
    elif 400 <= status_code < 500:
        return ErrorTaxonomyClass.PROVIDER_4XX
    elif 500 <= status_code < 600:
        return ErrorTaxonomyClass.PROVIDER_5XX
    return ErrorTaxonomyClass.NETWORK
