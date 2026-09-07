"""Request and result contracts for ELMOS Pricing & Billing engine.

Guarantees canonical JSON serialization, deterministic hashing, and strict validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import re
from typing import Any, Mapping

from .domain import ContractError, Currency, Money


def canonical_json(value: Any) -> str:
    """Serialize value to canonical, sorted JSON string."""
    def _default(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, Money):
            return {"amount": str(obj.amount), "currency": obj.currency.value}
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=_default, separators=(",", ":"))


def digest_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def require_text(value: Any, field_name: str, max_length: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized.encode("utf-8")) > max_length:
        raise ContractError(f"{field_name} exceeds max length of {max_length} bytes")
    return normalized


def validate_money(value: Any, field_name: str) -> Money:
    if isinstance(value, Money):
        return value
    if isinstance(value, (int, float, str, Decimal)):
        return Money(Decimal(str(value)))
    if isinstance(value, dict) and "amount" in value:
        cur = Currency(value.get("currency", "USD"))
        return Money(Decimal(str(value["amount"])), cur)
    raise ContractError(f"Invalid money value for {field_name}: {value}")


@dataclass(frozen=True)
class RequestContract:
    schema_version: str
    request_id: str
    tenant_id: str
    organization_id: str
    project_id: str
    actor_id: str
    idempotency_key: str
    inputs: Mapping[str, Any]

    @classmethod
    def parse(cls, data: Mapping[str, Any]) -> "RequestContract":
        return cls(
            schema_version=require_text(data.get("schema_version", "1.0"), "schema_version"),
            request_id=require_text(data.get("request_id", "req-001"), "request_id"),
            tenant_id=require_text(data.get("tenant_id", "default-tenant"), "tenant_id"),
            organization_id=require_text(data.get("organization_id", "default-org"), "organization_id"),
            project_id=require_text(data.get("project_id", "default-project"), "project_id"),
            actor_id=require_text(data.get("actor_id", "system"), "actor_id"),
            idempotency_key=require_text(data.get("idempotency_key", "idem-001"), "idempotency_key"),
            inputs=data.get("inputs", {}),
        )


@dataclass(frozen=True)
class ResultContract:
    skill_name: str
    status: str
    outputs: Mapping[str, Any]
    evidence_digest: str
    duration_ms: float
    error: str | None = None
