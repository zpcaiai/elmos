"""Typed fail-closed errors exposed by the bounded runtime."""

from __future__ import annotations


class GoldenRouteError(Exception):
    """Base class carrying a stable machine-readable error code."""

    code = "GOLDEN_ROUTE_ERROR"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def as_dict(self) -> dict[str, object]:
        return {
            "decision": "BLOCKED",
            "error": self.code,
            "message": self.message,
            "details": self.details,
            "customer_evidence_status": "NOT_RUN",
            "external_evidence_status": "NOT_RUN",
            "certification": "NOT_CERTIFIED",
        }


class CatalogValidationError(GoldenRouteError):
    code = "CATALOG_VALIDATION_FAILED"


class RequestValidationError(GoldenRouteError):
    code = "REQUEST_VALIDATION_FAILED"


class UnknownSkillError(GoldenRouteError):
    code = "UNKNOWN_SKILL"


class ExternalAdapterRequired(GoldenRouteError):
    code = "EXTERNAL_ADAPTER_REQUIRED"


class RunNotFound(GoldenRouteError):
    code = "RUN_NOT_FOUND"


class StateConflict(GoldenRouteError):
    code = "STATE_CONFLICT"


class IdempotencyConflict(GoldenRouteError):
    code = "IDEMPOTENCY_CONFLICT"


class EvidenceValidationError(GoldenRouteError):
    code = "EVIDENCE_VALIDATION_FAILED"


class SchemaMigrationRequired(GoldenRouteError):
    code = "STATE_SCHEMA_MIGRATION_REQUIRED"
