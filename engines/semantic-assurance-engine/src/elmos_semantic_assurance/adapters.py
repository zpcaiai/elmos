"""Explicit adapter boundary for native, proof and fuzz execution.

Repository content never selects a process, command, network destination or
credential.  A host application must register a trusted adapter out of band;
the semantic runtime only sends a typed plan and validates the returned
receipt.  Adapter receipts remain self-attested local evidence here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .canonical import canonical_value, validate_digest, validate_identifier
from .contracts import AssuranceScope


class AdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AdapterReceipt:
    adapter_id: str
    execution_id: str
    request_digest: str
    scope_digest: str
    status: str
    evidence_digest: str
    executor_id: str
    output: dict[str, Any]
    verifier_id: str | None = None
    signed: bool = False

    def __post_init__(self) -> None:
        validate_identifier(self.adapter_id, "receipt.adapterId")
        validate_identifier(self.execution_id, "receipt.executionId")
        validate_identifier(self.executor_id, "receipt.executorId")
        if self.verifier_id is not None:
            validate_identifier(self.verifier_id, "receipt.verifierId")
        validate_digest(self.request_digest, "receipt.requestDigest")
        validate_digest(self.scope_digest, "receipt.scopeDigest")
        validate_digest(self.evidence_digest, "receipt.evidenceDigest")
        if self.status not in {
            "PASS",
            "FAIL",
            "UNKNOWN",
            "TIMEOUT",
            "UNSUPPORTED",
            "COUNTEREXAMPLE",
        }:
            raise AdapterError("adapter receipt status is invalid")
        if self.verifier_id is not None and self.verifier_id == self.executor_id:
            raise AdapterError("adapter executor and verifier must be independent")
        canonical_value(self.output)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "executionId": self.execution_id,
            "requestDigest": validate_digest(self.request_digest),
            "scopeDigest": validate_digest(self.scope_digest),
            "status": self.status,
            "evidenceDigest": validate_digest(self.evidence_digest),
            "executorId": self.executor_id,
            "verifierId": self.verifier_id,
            "signed": self.signed,
            "output": canonical_value(self.output),
        }


class ExecutionAdapter(Protocol):
    adapter_id: str
    supported_actions: frozenset[str]

    def execute(
        self,
        plan: dict[str, Any],
        scope: AssuranceScope,
    ) -> AdapterReceipt:
        """Execute one typed plan without accepting an arbitrary shell string."""


@dataclass(frozen=True, slots=True)
class AdapterSet:
    native: ExecutionAdapter | None = None
    formal: ExecutionAdapter | None = None
    fuzz: ExecutionAdapter | None = None


__all__ = [
    "AdapterError",
    "AdapterReceipt",
    "AdapterSet",
    "ExecutionAdapter",
]
