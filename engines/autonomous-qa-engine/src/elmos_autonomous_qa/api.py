"""Authenticated in-process API surface for autonomous QA.

Transport hosts must construct :class:`TrustedIdentity`, including exact
project grants, from authenticated identity and trusted resource bindings,
never from request JSON.  This module intentionally does not start a network
listener or invent an authentication mechanism.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .artifacts import ArtifactError
from .contracts import (
    ContractError,
    HandlerOutputError,
    RuntimeRequest,
    digest_json,
    normalize_result,
    require_resource_id,
    strict_json,
)
from .control_plane import (
    DEFAULT_HISTORY_PAGE_SIZE,
    MAX_HISTORY_PAGE_SIZE,
    ControlPlaneError,
    EvidenceReceiptInvalid,
    EvidenceReceiptNotFound,
    IdempotencyConflict,
    IllegalTransition,
    QaControlPlane,
    ResourceQuotaExceeded,
    RunAlreadyExists,
    RunNotFound,
)
from .delivery_service import (
    DeliveryError,
    DeliveryStateError,
    TrustedDeliveryService,
)
from .skill_runtime import (
    SKILL_REGISTRY,
    SkillRuntimeError,
    dispatch_skill,
    resolve_skill,
)
from .trusted_services import (
    TrustedProjectRoots,
    TrustedSkillServices,
)


MAX_TRUSTED_ROLES = 64
MAX_TRUSTED_PROJECT_GRANTS = 1024


def _trusted_resource_id(value: Any, field: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{field} must be an exact string")
    try:
        normalized = require_resource_id(value, field)
    except ContractError as exc:
        raise ValueError(f"{field} is not a valid trusted resource identifier") from exc
    if normalized != value:
        raise ValueError(f"{field} must already be canonical")
    return value


@dataclass(frozen=True, slots=True)
class TrustedIdentity:
    tenant_id: str
    actor_id: str
    roles: frozenset[str]
    project_ids: frozenset[str]
    authenticated: bool = True

    def __post_init__(self) -> None:
        _trusted_resource_id(self.tenant_id, "tenant_id")
        _trusted_resource_id(self.actor_id, "actor_id")
        if type(self.authenticated) is not bool:
            raise TypeError("authenticated must be an exact boolean")
        for field, values, maximum in (
            ("roles", self.roles, MAX_TRUSTED_ROLES),
            ("project_ids", self.project_ids, MAX_TRUSTED_PROJECT_GRANTS),
        ):
            if type(values) is not frozenset:
                raise TypeError(f"{field} must be a frozenset")
            if len(values) > maximum:
                raise ValueError(f"{field} exceeds its trusted grant limit")
            for value in values:
                _trusted_resource_id(value, f"{field}[]")


@dataclass(frozen=True, slots=True)
class ApiResponse:
    status: int
    body: Mapping[str, Any]


class QaApi:
    """Route API requests onto the durable control plane and Skill runtime."""

    def __init__(
        self,
        control_plane: QaControlPlane,
        *,
        project_roots: Mapping[tuple[str, str], str | Path] | None = None,
        trusted_services: TrustedSkillServices | None = None,
        delivery_service: TrustedDeliveryService | None = None,
    ) -> None:
        if trusted_services is not None and project_roots is not None:
            raise ValueError(
                "project_roots and an explicit trusted_services binder are mutually exclusive"
            )
        self.control_plane = control_plane
        self.trusted_services = trusted_services or TrustedSkillServices(
            control_plane,
            project_roots=TrustedProjectRoots(project_roots),
        )
        if delivery_service is not None and type(delivery_service) is not TrustedDeliveryService:
            raise TypeError("delivery_service must be an exact TrustedDeliveryService")
        self.delivery_service = delivery_service

    @staticmethod
    def _normalize_trusted_skill_result(
        skill: str,
        request: Mapping[str, Any],
        operation: Mapping[str, Any],
    ) -> dict[str, Any]:
        alias = resolve_skill(skill)
        binding = SKILL_REGISTRY[alias]
        parsed = RuntimeRequest.parse(request)
        return normalize_result(
            skill=alias,
            source_id=binding.source_id,
            handler_id=binding.handler_id,
            operation_id=binding.operation_id,
            phase=binding.phase,
            mutating=binding.mutating,
            request=parsed,
            operation=operation,
        )

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if isinstance(value, Enum):
            return value.value
        if hasattr(value, "__dataclass_fields__"):
            return {key: QaApi._jsonable(item) for key, item in asdict(value).items()}
        if isinstance(value, Mapping):
            return {str(key): QaApi._jsonable(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [QaApi._jsonable(item) for item in value]
        return value

    @staticmethod
    def _require(identity: TrustedIdentity | None, role: str) -> TrustedIdentity:
        if type(identity) is not TrustedIdentity or not identity.authenticated:
            raise PermissionError("authenticated identity is required")
        if role not in identity.roles:
            raise PermissionError("required role is missing")
        return identity

    @staticmethod
    def _require_project(identity: TrustedIdentity, project_id: str) -> None:
        if project_id not in identity.project_ids:
            raise PermissionError("project resource grant is missing")

    def _authorized_run(
        self,
        identity: TrustedIdentity | None,
        role: str,
        run_id: str,
    ) -> tuple[TrustedIdentity, Any]:
        caller = self._require(identity, role)
        run = self.control_plane.get_run(
            tenant_id=caller.tenant_id,
            run_id=run_id,
        )
        self._require_project(caller, run.project_id)
        return caller, run

    @staticmethod
    def _object(value: Any) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise ValueError("request body must be an object")
        try:
            normalized = strict_json(value, "request body")
        except RecursionError as exc:
            raise ValueError("request body exceeds the nesting limit") from exc
        if not isinstance(normalized, dict):
            raise ValueError("request body must be an object")
        return normalized

    @staticmethod
    def _route_text(value: Any, field: str, *, maximum: int) -> str:
        if type(value) is not str or not value:
            raise ValueError(f"{field} must be a non-empty exact string")
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise ValueError(f"{field} contains invalid Unicode") from exc
        if len(encoded) > maximum or any(
            ord(character) < 32 or ord(character) == 127 for character in value
        ):
            raise ValueError(f"{field} exceeds its bound or contains a control character")
        return value

    @staticmethod
    def _required_string(payload: Mapping[str, Any], field: str) -> str:
        value = payload.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _optional_string(
        payload: Mapping[str, Any],
        field: str,
        *,
        default: str | None = None,
        nullable: bool = False,
    ) -> str | None:
        if field not in payload:
            return default
        value = payload[field]
        if value is None and nullable:
            return None
        if not isinstance(value, str) or not value:
            raise ValueError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _optional_nonnegative_int(
        payload: Mapping[str, Any], field: str, *, default: int
    ) -> int:
        value = payload.get(field, default)
        if type(value) is not int or value < 0:
            raise ValueError(f"{field} must be a non-negative integer")
        return value

    @staticmethod
    def _history_limit(payload: Mapping[str, Any]) -> int:
        value = payload.get("limit", DEFAULT_HISTORY_PAGE_SIZE)
        if type(value) is not int or not 1 <= value <= MAX_HISTORY_PAGE_SIZE:
            raise ValueError(
                f"limit must be between 1 and {MAX_HISTORY_PAGE_SIZE}"
            )
        return value

    @classmethod
    def _object_field(
        cls,
        payload: Mapping[str, Any],
        field: str,
        *,
        default_empty: bool = False,
    ) -> dict[str, Any]:
        if field not in payload:
            if default_empty:
                return {}
            raise ValueError(f"{field} is required")
        return cls._object(payload[field])

    def handle(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None,
        identity: TrustedIdentity | None,
    ) -> ApiResponse:
        try:
            method = self._route_text(method, "method", maximum=16)
            path = self._route_text(path, "path", maximum=1024)
            normalized_method = method.upper()
            payload = self._object({} if body is None else body)
            if path == "/api/v1/qa/capabilities" and normalized_method == "GET":
                caller = self._require(identity, "qa:read")
                return ApiResponse(
                    200,
                    {
                        "schema_version": "1.0",
                        "tenant_id": caller.tenant_id,
                        "skills": 40,
                        "local_runtime": "LOCAL_EXECUTED",
                        "external_evidence": "NOT_RUN",
                        "certification": "NOT_CERTIFIED",
                    },
                )
            if path == "/api/v1/qa/runs" and normalized_method == "POST":
                caller = self._require(identity, "qa:write")
                project_id = self._required_string(payload, "project_id")
                self._require_project(caller, project_id)
                if "run_id" in payload:
                    run_id = self._required_string(payload, "run_id")
                else:
                    run_id = "run-" + digest_json(
                        {
                            "tenant": caller.tenant_id,
                            "project": project_id,
                            "key": self._required_string(payload, "idempotency_key"),
                        }
                    )[7:31]
                run = self.control_plane.create_run(
                    tenant_id=caller.tenant_id,
                    run_id=run_id,
                    project_id=project_id,
                    mode=self._required_string(payload, "mode"),
                    payload=self._object_field(
                        payload, "payload", default_empty=True
                    ),
                    idempotency_key=self._required_string(
                        payload, "idempotency_key"
                    ),
                    actor=caller.actor_id,
                )
                return ApiResponse(201, self._jsonable(run))
            if path == "/api/v1/qa/evidence" and normalized_method == "POST":
                run_id = self._required_string(payload, "run_id")
                caller, _ = self._authorized_run(
                    identity, "qa:evidence:verify", run_id
                )
                receipt = self.control_plane.register_verified_evidence(
                    tenant_id=caller.tenant_id,
                    receipt_id=self._required_string(payload, "receipt_id"),
                    run_id=run_id,
                    scope=self._required_string(payload, "scope"),
                    subject_digest=self._required_string(payload, "subject_digest"),
                    evidence_digest=self._required_string(payload, "evidence_digest"),
                    artifact_digest=self._required_string(payload, "artifact_digest"),
                    authorization_ref=self._required_string(
                        payload, "authorization_ref"
                    ),
                    executor_id=self._required_string(payload, "executor_id"),
                    verifier_id=self._required_string(payload, "verifier_id"),
                    valid_until=self._required_string(payload, "valid_until"),
                    registered_by=caller.actor_id,
                )
                return ApiResponse(201, self._jsonable(receipt))
            evidence_prefix = "/api/v1/qa/evidence/"
            if (
                path.startswith(evidence_prefix)
                and path.endswith(":revoke")
                and normalized_method == "POST"
            ):
                caller = self._require(identity, "qa:evidence:revoke")
                if payload:
                    raise ValueError("evidence revocation body must be empty")
                receipt_id = path[len(evidence_prefix) : -len(":revoke")]
                if not receipt_id:
                    raise ValueError("receipt_id path segment is required")
                existing_receipt = self.control_plane.get_verified_evidence(
                    tenant_id=caller.tenant_id,
                    receipt_id=receipt_id,
                )
                receipt_run = self.control_plane.get_run(
                    tenant_id=caller.tenant_id,
                    run_id=existing_receipt.run_id,
                )
                self._require_project(caller, receipt_run.project_id)
                receipt = self.control_plane.revoke_verified_evidence(
                    tenant_id=caller.tenant_id,
                    receipt_id=receipt_id,
                    actor=caller.actor_id,
                )
                return ApiResponse(200, self._jsonable(receipt))
            skill_prefix = "/api/v1/qa/skills/"
            if (
                path.startswith(skill_prefix)
                and path.endswith(":execute")
                and normalized_method == "POST"
            ):
                if type(identity) is not TrustedIdentity or not identity.authenticated:
                    raise PermissionError("authenticated identity is required")
                skill = path[len(skill_prefix) : -len(":execute")]
                if not skill:
                    raise SkillRuntimeError("Skill identifier is required")
                alias = resolve_skill(skill)
                binding = SKILL_REGISTRY[alias]
                source_id = binding.source_id
                required_role = {
                    "38-project-output-bundle-publishing": "qa:publish",
                    "39-output-versioning-retention": "qa:lifecycle",
                }.get(source_id, "qa:write")
                caller = self._require(identity, required_role)
                project_id = self._required_string(payload, "project_id")
                self._require_project(caller, project_id)
                request = {
                    "schema_version": "1.0",
                    "request_id": self._optional_string(
                        payload,
                        "request_id",
                        default="request-" + digest_json(payload)[7:23],
                    ),
                    "tenant_id": caller.tenant_id,
                    "project_id": project_id,
                    "actor_id": caller.actor_id,
                    "idempotency_key": (
                        self._required_string(payload, "idempotency_key")
                        if binding.mutating
                        else self._optional_string(
                            payload, "idempotency_key", nullable=True
                        )
                    ),
                    "inputs": self._object_field(
                        payload, "inputs", default_empty=True
                    ),
                    "policy": self._object_field(
                        payload, "policy", default_empty=True
                    ),
                    "capabilities": self._object_field(
                        payload, "capabilities", default_empty=True
                    ),
                }
                if source_id == "00-qa-control-plane":
                    parsed = RuntimeRequest.parse(request)
                    result = self._normalize_trusted_skill_result(
                        alias,
                        request,
                        self.trusted_services.execute_control_plane(parsed),
                    )
                elif source_id == "01-project-context-ingestion":
                    parsed = RuntimeRequest.parse(request)
                    result = self._normalize_trusted_skill_result(
                        alias,
                        request,
                        self.trusted_services.execute_project_context(parsed),
                    )
                elif source_id in {
                    "37-test-source-materialization",
                    "38-project-output-bundle-publishing",
                    "39-output-versioning-retention",
                } and self.delivery_service is not None:
                    parsed = RuntimeRequest.parse(request)
                    operation = {
                        "37-test-source-materialization": (
                            self.delivery_service.execute_materialization
                        ),
                        "38-project-output-bundle-publishing": (
                            self.delivery_service.execute_publishing
                        ),
                        "39-output-versioning-retention": (
                            self.delivery_service.execute_lifecycle
                        ),
                    }[source_id](parsed)
                    result = self._normalize_trusted_skill_result(
                        alias,
                        request,
                        operation,
                    )
                else:
                    result = dispatch_skill(alias, request)
                if result["state"] in {"SUCCEEDED", "PARTIAL"}:
                    status = 200
                elif result["retryable"]:
                    status = 503
                elif result["state"] == "FAILED":
                    status = 500
                elif result["code"] == "TRUSTED_DELIVERY_BINDER_REQUIRED":
                    status = 503
                elif source_id in {
                    "37-test-source-materialization",
                    "38-project-output-bundle-publishing",
                    "39-output-versioning-retention",
                }:
                    status = 409
                else:
                    status = 422
                return ApiResponse(status, result)
            run_prefix = "/api/v1/qa/runs/"
            if path.startswith(run_prefix):
                remainder = path[len(run_prefix) :]
                if remainder.endswith("/events") and normalized_method == "GET":
                    if set(payload) - {"after_sequence", "limit"}:
                        raise ValueError("event page body contains unsupported fields")
                    run_id = remainder[: -len("/events")]
                    caller, _ = self._authorized_run(identity, "qa:read", run_id)
                    after_sequence = self._optional_nonnegative_int(
                        payload, "after_sequence", default=0
                    )
                    limit = self._history_limit(payload)
                    events = self.control_plane.list_events(
                        tenant_id=caller.tenant_id,
                        run_id=run_id,
                        after_sequence=after_sequence,
                        limit=limit,
                    )
                    return ApiResponse(
                        200,
                        {
                            "events": self._jsonable(events),
                            "page_limit": limit,
                            "next_after_sequence": (
                                events[-1].sequence if len(events) == limit else None
                            ),
                        },
                    )
                if remainder.endswith("/audit") and normalized_method == "GET":
                    if set(payload) - {"after_audit_id", "limit"}:
                        raise ValueError("audit page body contains unsupported fields")
                    run_id = remainder[: -len("/audit")]
                    caller, _ = self._authorized_run(identity, "qa:audit", run_id)
                    after_audit_id = self._optional_nonnegative_int(
                        payload, "after_audit_id", default=0
                    )
                    limit = self._history_limit(payload)
                    audit = self.control_plane.list_audit(
                        tenant_id=caller.tenant_id,
                        run_id=run_id,
                        after_audit_id=after_audit_id,
                        limit=limit,
                    )
                    return ApiResponse(
                        200,
                        {
                            "audit": self._jsonable(audit),
                            "page_limit": limit,
                            "next_after_audit_id": (
                                audit[-1].audit_id if len(audit) == limit else None
                            ),
                        },
                    )
                if ":" in remainder and normalized_method == "POST":
                    run_id, action = remainder.rsplit(":", 1)
                    caller, _ = self._authorized_run(
                        identity,
                        "qa:approve" if action == "approve" else "qa:write",
                        run_id,
                    )
                    if action == "retry":
                        run = self.control_plane.retry_run(
                            tenant_id=caller.tenant_id,
                            source_run_id=run_id,
                            new_run_id=self._required_string(
                                payload, "new_run_id"
                            ),
                            idempotency_key=self._required_string(
                                payload, "idempotency_key"
                            ),
                            actor=caller.actor_id,
                        )
                    else:
                        run = self.control_plane.transition(
                            tenant_id=caller.tenant_id,
                            run_id=run_id,
                            action=action,
                            idempotency_key=self._required_string(
                                payload, "idempotency_key"
                            ),
                            actor=caller.actor_id,
                            details=self._object_field(
                                payload, "details", default_empty=True
                            ),
                        )
                    return ApiResponse(200, self._jsonable(run))
                if normalized_method == "GET":
                    _, run = self._authorized_run(identity, "qa:read", remainder)
                    return ApiResponse(200, self._jsonable(run))
            return ApiResponse(404, {"error_code": "QA_ROUTE_NOT_FOUND"})
        except PermissionError:
            return ApiResponse(403, {"error_code": "QA_ACCESS_DENIED", "retryable": False})
        except RunNotFound:
            return ApiResponse(404, {"error_code": "QA_RUN_NOT_FOUND", "retryable": False})
        except EvidenceReceiptNotFound:
            return ApiResponse(
                404,
                {"error_code": "QA_EVIDENCE_RECEIPT_NOT_FOUND", "retryable": False},
            )
        except RunAlreadyExists:
            return ApiResponse(
                409, {"error_code": "QA_RUN_ALREADY_EXISTS", "retryable": False}
            )
        except IdempotencyConflict:
            return ApiResponse(
                409, {"error_code": "QA_IDEMPOTENCY_CONFLICT", "retryable": False}
            )
        except ResourceQuotaExceeded:
            return ApiResponse(
                429,
                {"error_code": "QA_RESOURCE_QUOTA_EXCEEDED", "retryable": False},
            )
        except IllegalTransition as exc:
            reason_code = str(exc)
            if "EVIDENCE" in reason_code or reason_code.startswith(
                ("VERIFIER_", "EXECUTOR_")
            ):
                error_code = "QA_EVIDENCE_REJECTED"
            elif "APPROVAL" in reason_code or reason_code.startswith("INDEPENDENT_"):
                error_code = "QA_APPROVAL_REJECTED"
            else:
                error_code = "QA_ILLEGAL_TRANSITION"
            return ApiResponse(
                409,
                {
                    "error_code": error_code,
                    "reason_code": reason_code,
                    "retryable": False,
                },
            )
        except EvidenceReceiptInvalid:
            return ApiResponse(
                422, {"error_code": "QA_EVIDENCE_REJECTED", "retryable": False}
            )
        except HandlerOutputError:
            return ApiResponse(
                500, {"error_code": "QA_HANDLER_OUTPUT_INVALID", "retryable": False}
            )
        except DeliveryStateError:
            return ApiResponse(
                500, {"error_code": "QA_DELIVERY_STATE_ERROR", "retryable": False}
            )
        except (DeliveryError, ArtifactError):
            return ApiResponse(
                500, {"error_code": "QA_DELIVERY_ERROR", "retryable": False}
            )
        except sqlite3.IntegrityError:
            return ApiResponse(
                500,
                {"error_code": "QA_CONTROL_PLANE_INTEGRITY_ERROR", "retryable": False},
            )
        except sqlite3.OperationalError:
            return ApiResponse(
                503, {"error_code": "QA_STORAGE_UNAVAILABLE", "retryable": True}
            )
        except sqlite3.DatabaseError:
            return ApiResponse(
                500,
                {"error_code": "QA_CONTROL_PLANE_INTEGRITY_ERROR", "retryable": False},
            )
        except SkillRuntimeError:
            return ApiResponse(404, {"error_code": "QA_SKILL_NOT_FOUND", "retryable": False})
        except ControlPlaneError:
            return ApiResponse(
                500,
                {"error_code": "QA_CONTROL_PLANE_INTEGRITY_ERROR", "retryable": False},
            )
        except (TypeError, ValueError):
            return ApiResponse(
                422, {"error_code": "QA_REQUEST_INVALID", "retryable": False}
            )
