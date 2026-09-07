"""Trusted cache-affinity inventory, dispatch, and placement receipts.

Pure affinity scoring intentionally has no side effects.  This module binds a
server-owned attested inventory to a server-owned placement sink, records every
explicit rejection, and retries only a bounded number of distinct candidates.
Unknown sink outcomes are never retried automatically.
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .affinity import (
    AffinityAuthorizationResolver,
    AffinityCandidate,
    AffinityDecision,
    AffinityRequest,
    AttestedAffinityRegistry,
    route_affinity,
)
from .canonical import digest_of, require_digest
from .clock import SYSTEM_CLOCK, Clock
from .errors import (
    ContractViolation,
    IdempotencyConflict,
    IdempotencyOutcomeUnknown,
    PermissionDenied,
)

AFFINITY_PLACEMENT_SCHEMA_VERSION = "1.0.0"
AFFINITY_PLACEMENT_RECEIPT_KIND = "elmos.cache-affinity-placement-receipt/v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,127}$")


def _identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ContractViolation(f"{field_name} must be a bounded identifier")
    return value


def _timestamp(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(float(value)) or value < 0:
        raise ContractViolation(f"{field_name} must be finite and non-negative")
    return float(value)


def _tenant_scope_digest(tenant_id: str, project_id: str) -> str:
    return digest_of(
        {
            "tenant_id": _identifier(tenant_id, "tenant_id"),
            "project_id": _identifier(project_id, "project_id"),
        }
    )


@dataclass(frozen=True, slots=True)
class RunnerInventorySnapshot:
    """One immutable, already-filtered view from a trusted inventory source."""

    tenant_id: str
    project_id: str
    source_identity_digest: str
    observed_at: float
    affinity_key: str
    candidates: tuple[AffinityCandidate, ...]

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.source_identity_digest)
        object.__setattr__(self, "observed_at", _timestamp(self.observed_at, "observed_at"))
        require_digest(self.affinity_key)
        if any(not isinstance(item, AffinityCandidate) for item in self.candidates):
            raise ContractViolation("runner inventory returned an invalid candidate type")
        target_ids = tuple(item.target_id for item in self.candidates)
        if len(target_ids) != len(set(target_ids)):
            raise ContractViolation("runner inventory contains duplicate target IDs")
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(self.candidates, key=lambda item: item.target_id)),
        )

    @property
    def inventory_digest(self) -> str:
        return digest_of(
            {
                "schema_version": AFFINITY_PLACEMENT_SCHEMA_VERSION,
                "tenant_id": self.tenant_id,
                "project_id": self.project_id,
                "source_identity_digest": self.source_identity_digest,
                "observed_at": self.observed_at,
                "affinity_key": self.affinity_key,
                "candidates": [item.attestation_document() for item in self.candidates],
            }
        )


class RunnerInventorySource(Protocol):
    """Trusted source installed at service composition time, never by a request."""

    def snapshot(
        self,
        tenant_id: str,
        project_id: str,
        request: AffinityRequest,
        *,
        now: float,
    ) -> RunnerInventorySnapshot: ...


class AttestedRegistryInventorySource:
    """Adapt :class:`AttestedAffinityRegistry` to an immutable snapshot."""

    def __init__(
        self,
        registry: AttestedAffinityRegistry,
        *,
        source_identity_digest: str,
    ) -> None:
        if not isinstance(registry, AttestedAffinityRegistry):
            raise ContractViolation("runner inventory source requires an attested registry")
        self._registry = registry
        self._source_identity_digest = require_digest(source_identity_digest)

    def snapshot(
        self,
        tenant_id: str,
        project_id: str,
        request: AffinityRequest,
        *,
        now: float,
    ) -> RunnerInventorySnapshot:
        observed_at = _timestamp(now, "now")
        candidates = self._registry.candidates(
            tenant_id,
            project_id,
            request,
            observed_at,
        )
        return RunnerInventorySnapshot(
            tenant_id=tenant_id,
            project_id=project_id,
            source_identity_digest=self._source_identity_digest,
            observed_at=observed_at,
            affinity_key=request.affinity_key,
            candidates=candidates,
        )


class PlacementDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class PlacementCommand:
    """Exact placement effect offered to a trusted sink."""

    tenant_id: str
    project_id: str
    principal_digest: str
    request_id: str
    target_id: str
    attempt: int
    affinity_key: str
    inventory_digest: str
    decision_digest: str
    candidate_digest: str

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.principal_digest)
        _identifier(self.request_id, "request_id")
        _identifier(self.target_id, "target_id")
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ContractViolation("placement attempt must be a positive integer")
        require_digest(self.affinity_key)
        require_digest(self.inventory_digest)
        require_digest(self.decision_digest)
        require_digest(self.candidate_digest)

    def to_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "principal_digest": self.principal_digest,
            "request_id": self.request_id,
            "target_id": self.target_id,
            "attempt": self.attempt,
            "affinity_key": self.affinity_key,
            "inventory_digest": self.inventory_digest,
            "decision_digest": self.decision_digest,
            "candidate_digest": self.candidate_digest,
        }

    @property
    def command_digest(self) -> str:
        return digest_of(self.to_dict())


@dataclass(frozen=True, slots=True)
class PlacementSinkResult:
    """Explicit sink acknowledgement; exceptions are outcome-unknown instead."""

    disposition: PlacementDisposition
    reason_code: str
    command_digest: str
    sink_receipt_digest: str
    placement_id: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.disposition, PlacementDisposition):
            raise ContractViolation("placement sink disposition is invalid")
        _identifier(self.reason_code, "reason_code")
        require_digest(self.command_digest)
        require_digest(self.sink_receipt_digest)
        if not isinstance(self.retryable, bool):
            raise ContractViolation("placement retryable flag must be boolean")
        if self.disposition is PlacementDisposition.ACCEPTED:
            if self.placement_id is None:
                raise ContractViolation("accepted placement requires a placement ID")
            _identifier(self.placement_id, "placement_id")
            if self.retryable:
                raise ContractViolation("accepted placement cannot be retryable")
        elif self.placement_id is not None:
            raise ContractViolation("rejected placement cannot carry a placement ID")


class PlacementSink(Protocol):
    """Trusted scheduler/dispatcher boundary installed by the host."""

    def place(self, command: PlacementCommand) -> PlacementSinkResult: ...


@dataclass(frozen=True, slots=True)
class PlacementAttempt:
    attempt: int
    target_id: str
    candidate_digest: str
    decision_digest: str
    command_digest: str
    disposition: PlacementDisposition
    reason_code: str
    sink_receipt_digest: str
    placement_id: str | None
    retryable: bool

    def __post_init__(self) -> None:
        if isinstance(self.attempt, bool) or not isinstance(self.attempt, int) or self.attempt < 1:
            raise ContractViolation("placement attempt must be a positive integer")
        _identifier(self.target_id, "target_id")
        require_digest(self.candidate_digest)
        require_digest(self.decision_digest)
        require_digest(self.command_digest)
        if not isinstance(self.disposition, PlacementDisposition):
            raise ContractViolation("placement attempt disposition is invalid")
        _identifier(self.reason_code, "reason_code")
        require_digest(self.sink_receipt_digest)
        if not isinstance(self.retryable, bool):
            raise ContractViolation("placement attempt retryable flag must be boolean")
        if self.disposition is PlacementDisposition.ACCEPTED:
            if self.placement_id is None:
                raise ContractViolation("accepted placement attempt requires a placement ID")
            _identifier(self.placement_id, "placement_id")
            if self.retryable:
                raise ContractViolation("accepted placement attempt cannot be retryable")
        elif self.placement_id is not None:
            raise ContractViolation("rejected placement attempt cannot carry a placement ID")

    @classmethod
    def from_result(
        cls,
        command: PlacementCommand,
        result: PlacementSinkResult,
    ) -> PlacementAttempt:
        return cls(
            attempt=command.attempt,
            target_id=command.target_id,
            candidate_digest=command.candidate_digest,
            decision_digest=command.decision_digest,
            command_digest=command.command_digest,
            disposition=result.disposition,
            reason_code=result.reason_code,
            sink_receipt_digest=result.sink_receipt_digest,
            placement_id=result.placement_id,
            retryable=result.retryable,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "target_id": self.target_id,
            "candidate_digest": self.candidate_digest,
            "decision_digest": self.decision_digest,
            "command_digest": self.command_digest,
            "disposition": self.disposition.value,
            "reason_code": self.reason_code,
            "sink_receipt_digest": self.sink_receipt_digest,
            "placement_id": self.placement_id,
            "retryable": self.retryable,
        }


class PlacementOutcome(StrEnum):
    PLACED = "PLACED"
    NO_COMPATIBLE_TARGET = "NO_COMPATIBLE_TARGET"
    SINK_REJECTED = "SINK_REJECTED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED"


@dataclass(frozen=True, slots=True)
class AffinityPlacementReceipt:
    tenant_id: str
    project_id: str
    principal_digest: str
    request_id: str
    affinity_key: str
    inventory_digest: str
    outcome: PlacementOutcome
    selected_target: str | None
    candidate_digest: str | None
    final_decision_digest: str
    attempts: tuple[PlacementAttempt, ...]

    def __post_init__(self) -> None:
        _identifier(self.tenant_id, "tenant_id")
        _identifier(self.project_id, "project_id")
        require_digest(self.principal_digest)
        _identifier(self.request_id, "request_id")
        require_digest(self.affinity_key)
        require_digest(self.inventory_digest)
        if not isinstance(self.outcome, PlacementOutcome):
            raise ContractViolation("placement receipt outcome is invalid")
        require_digest(self.final_decision_digest)
        attempts = tuple(self.attempts)
        if any(not isinstance(item, PlacementAttempt) for item in attempts):
            raise ContractViolation("placement receipt contains an invalid attempt")
        object.__setattr__(self, "attempts", attempts)
        for item in attempts:
            expected_command = PlacementCommand(
                tenant_id=self.tenant_id,
                project_id=self.project_id,
                principal_digest=self.principal_digest,
                request_id=self.request_id,
                target_id=item.target_id,
                attempt=item.attempt,
                affinity_key=self.affinity_key,
                inventory_digest=self.inventory_digest,
                decision_digest=item.decision_digest,
                candidate_digest=item.candidate_digest,
            )
            if item.command_digest != expected_command.command_digest:
                raise ContractViolation("placement attempt command binding is invalid")
        if self.outcome is PlacementOutcome.PLACED:
            if self.selected_target is None or self.candidate_digest is None or not self.attempts:
                raise ContractViolation("placed receipt lacks its selected candidate")
            _identifier(self.selected_target, "selected_target")
            require_digest(self.candidate_digest)
            last = self.attempts[-1]
            if (
                last.disposition is not PlacementDisposition.ACCEPTED
                or last.target_id != self.selected_target
                or last.candidate_digest != self.candidate_digest
            ):
                raise ContractViolation("placed receipt does not match the accepted sink attempt")
        elif self.selected_target is not None or self.candidate_digest is not None:
            raise ContractViolation("non-placement receipt cannot claim a selected candidate")
        if tuple(item.attempt for item in self.attempts) != tuple(range(1, len(self.attempts) + 1)):
            raise ContractViolation("placement receipt attempts are not contiguous")
        if len({item.target_id for item in self.attempts}) != len(self.attempts):
            raise ContractViolation("placement receipt retried the same target")

    def unsigned_document(self) -> dict[str, object]:
        return {
            "schema_version": AFFINITY_PLACEMENT_SCHEMA_VERSION,
            "kind": AFFINITY_PLACEMENT_RECEIPT_KIND,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "principal_digest": self.principal_digest,
            "request_id": self.request_id,
            "affinity_key": self.affinity_key,
            "inventory_digest": self.inventory_digest,
            "outcome": self.outcome.value,
            "selected_target": self.selected_target,
            "candidate_digest": self.candidate_digest,
            "final_decision_digest": self.final_decision_digest,
            "attempt_count": len(self.attempts),
            "attempts": [item.to_dict() for item in self.attempts],
            "external_fleet_evidence": "NOT_RUN",
        }

    @property
    def receipt_digest(self) -> str:
        return digest_of(self.unsigned_document())

    def to_dict(self) -> dict[str, object]:
        document = self.unsigned_document()
        document["receipt_digest"] = self.receipt_digest
        return document


@dataclass(frozen=True, slots=True)
class AffinityPlacementResult:
    decision: AffinityDecision
    receipt: AffinityPlacementReceipt

    @property
    def placed(self) -> bool:
        return self.receipt.outcome is PlacementOutcome.PLACED


class AffinityPlacementService:
    """Authorize, snapshot, rank, dispatch, and receipt one placement request."""

    def __init__(
        self,
        *,
        inventory_source: RunnerInventorySource,
        placement_sink: PlacementSink,
        authorization_resolver: AffinityAuthorizationResolver,
        clock: Clock = SYSTEM_CLOCK,
        max_attempts: int = 3,
    ) -> None:
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or not 1 <= max_attempts <= 32:
            raise ContractViolation("max placement attempts must be between 1 and 32")
        self._inventory_source = inventory_source
        self._placement_sink = placement_sink
        self._authorization_resolver = authorization_resolver
        self._clock = clock
        self._max_attempts = max_attempts
        # Placement is a side-effecting boundary.  Keep a per-service
        # singleflight/replay ledger so an identical request cannot dispatch
        # twice while its caller retries.  A request-id collision with changed
        # routing inputs is a hard idempotency conflict, never a new placement.
        self._replay_lock = threading.RLock()
        self._replays: dict[
            tuple[str, str, str, str], tuple[str, AffinityPlacementResult]
        ] = {}

    def place(
        self,
        *,
        tenant_id: str,
        project_id: str,
        principal_digest: str,
        request_id: str,
        request: AffinityRequest,
    ) -> AffinityPlacementResult:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        require_digest(principal_digest)
        _identifier(request_id, "request_id")
        if not isinstance(request, AffinityRequest):
            raise ContractViolation("placement requires a typed affinity request")
        replay_key = (tenant_id, project_id, principal_digest, request_id)
        request_digest = digest_of(
            {
                "affinity_key": request.affinity_key,
                "required_capacity": request.required_capacity,
            }
        )
        with self._replay_lock:
            replay = self._replays.get(replay_key)
            if replay is not None:
                if replay[0] != request_digest:
                    raise IdempotencyConflict(
                        "placement request ID was reused for different routing inputs",
                        request_id=request_id,
                    )
                return replay[1]
            result = self._place_uncached(
                tenant_id=tenant_id,
                project_id=project_id,
                principal_digest=principal_digest,
                request_id=request_id,
                request=request,
            )
            self._replays[replay_key] = (request_digest, result)
            return result

    def _place_uncached(
        self,
        *,
        tenant_id: str,
        project_id: str,
        principal_digest: str,
        request_id: str,
        request: AffinityRequest,
    ) -> AffinityPlacementResult:
        _identifier(tenant_id, "tenant_id")
        _identifier(project_id, "project_id")
        require_digest(principal_digest)
        _identifier(request_id, "request_id")
        if not isinstance(request, AffinityRequest):
            raise ContractViolation("placement requires a typed affinity request")
        expected_tenant_scope = _tenant_scope_digest(tenant_id, project_id)
        if request.tenant_scope_digest != expected_tenant_scope:
            raise PermissionDenied("affinity request tenant scope is not authorized")

        authorization = self._authorization_resolver.resolve(
            principal_digest,
            tenant_id,
            project_id,
            request_id,
        )
        if (
            not authorization.allowed
            or authorization.tenant_id != tenant_id
            or authorization.project_id != project_id
            or authorization.principal_digest != principal_digest
            or authorization.authorization_scope_digest != request.authorization_scope_digest
        ):
            raise PermissionDenied("affinity placement authorization scope mismatch")

        snapshot = self._inventory_source.snapshot(
            tenant_id,
            project_id,
            request,
            now=self._clock.now(),
        )
        self._validate_snapshot(snapshot, tenant_id, project_id, request)
        remaining = list(snapshot.candidates)
        attempts: list[PlacementAttempt] = []
        final_decision = route_affinity(request, remaining)
        outcome = PlacementOutcome.NO_COMPATIBLE_TARGET
        selected_target: str | None = None
        selected_candidate_digest: str | None = None

        while final_decision.selected_target is not None and len(attempts) < self._max_attempts:
            target_id = final_decision.selected_target
            selected = next(item for item in remaining if item.target_id == target_id)
            decision_digest = digest_of(final_decision.to_dict())
            candidate_digest = digest_of(selected.attestation_document())
            command = PlacementCommand(
                tenant_id=tenant_id,
                project_id=project_id,
                principal_digest=principal_digest,
                request_id=request_id,
                target_id=target_id,
                attempt=len(attempts) + 1,
                affinity_key=request.affinity_key,
                inventory_digest=snapshot.inventory_digest,
                decision_digest=decision_digest,
                candidate_digest=candidate_digest,
            )
            try:
                sink_result = self._placement_sink.place(command)
            except Exception as exc:
                raise IdempotencyOutcomeUnknown(
                    "placement sink outcome is unknown and cannot be retried",
                    target_id=target_id,
                    command_digest=command.command_digest,
                ) from exc
            if not isinstance(sink_result, PlacementSinkResult):
                raise ContractViolation("placement sink returned an invalid result type")
            if sink_result.command_digest != command.command_digest:
                raise ContractViolation("placement sink receipt is bound to a different command")
            attempts.append(PlacementAttempt.from_result(command, sink_result))
            if sink_result.disposition is PlacementDisposition.ACCEPTED:
                outcome = PlacementOutcome.PLACED
                selected_target = target_id
                selected_candidate_digest = candidate_digest
                break

            remaining = [item for item in remaining if item.target_id != target_id]
            if not sink_result.retryable:
                outcome = PlacementOutcome.SINK_REJECTED
                break
            if len(attempts) >= self._max_attempts:
                outcome = PlacementOutcome.RETRY_EXHAUSTED
                break
            final_decision = route_affinity(request, remaining)
        else:
            if attempts and final_decision.selected_target is None:
                outcome = PlacementOutcome.RETRY_EXHAUSTED

        final_decision_digest = digest_of(final_decision.to_dict())
        if outcome is PlacementOutcome.PLACED:
            final_decision_digest = attempts[-1].decision_digest
        receipt = AffinityPlacementReceipt(
            tenant_id=tenant_id,
            project_id=project_id,
            principal_digest=principal_digest,
            request_id=request_id,
            affinity_key=request.affinity_key,
            inventory_digest=snapshot.inventory_digest,
            outcome=outcome,
            selected_target=selected_target,
            candidate_digest=selected_candidate_digest,
            final_decision_digest=final_decision_digest,
            attempts=tuple(attempts),
        )
        verify_affinity_placement_receipt(receipt.to_dict())
        return AffinityPlacementResult(final_decision, receipt)

    @staticmethod
    def _validate_snapshot(
        snapshot: RunnerInventorySnapshot,
        tenant_id: str,
        project_id: str,
        request: AffinityRequest,
    ) -> None:
        if not isinstance(snapshot, RunnerInventorySnapshot):
            raise ContractViolation("runner inventory source returned an invalid snapshot")
        if (
            snapshot.tenant_id != tenant_id
            or snapshot.project_id != project_id
            or snapshot.affinity_key != request.affinity_key
        ):
            raise ContractViolation("runner inventory snapshot scope mismatch")
        for candidate in snapshot.candidates:
            if (
                candidate.tenant_scope_digest != request.tenant_scope_digest
                or candidate.authorization_scope_digest != request.authorization_scope_digest
                or not candidate.authorized
            ):
                raise ContractViolation(
                    "runner inventory returned a foreign or unauthorized candidate",
                    target_id=candidate.target_id,
                )


def verify_affinity_placement_receipt(document: Mapping[str, Any]) -> None:
    """Verify the top-level receipt digest and its accepted-attempt binding."""

    required = frozenset(
        {
            "schema_version",
            "kind",
            "tenant_id",
            "project_id",
            "principal_digest",
            "request_id",
            "affinity_key",
            "inventory_digest",
            "outcome",
            "selected_target",
            "candidate_digest",
            "final_decision_digest",
            "attempt_count",
            "attempts",
            "external_fleet_evidence",
            "receipt_digest",
        }
    )
    if not isinstance(document, Mapping) or set(document) != required:
        raise ContractViolation("affinity placement receipt has an invalid shape")
    if (
        document.get("schema_version") != AFFINITY_PLACEMENT_SCHEMA_VERSION
        or document.get("kind") != AFFINITY_PLACEMENT_RECEIPT_KIND
        or document.get("external_fleet_evidence") != "NOT_RUN"
    ):
        raise ContractViolation("affinity placement receipt boundary is invalid")
    _identifier_value(document.get("tenant_id"), "tenant_id")
    _identifier_value(document.get("project_id"), "project_id")
    _digest_value(document.get("principal_digest"), "principal_digest")
    _identifier_value(document.get("request_id"), "request_id")
    _digest_value(document.get("affinity_key"), "affinity_key")
    _digest_value(document.get("inventory_digest"), "inventory_digest")
    _digest_value(document.get("final_decision_digest"), "final_decision_digest")
    outcome_raw = _identifier_value(document.get("outcome"), "outcome")
    try:
        outcome = PlacementOutcome(outcome_raw)
    except ValueError as exc:
        raise ContractViolation("affinity placement receipt outcome is invalid") from exc
    attempts = document.get("attempts")
    if (
        not isinstance(attempts, list)
        or isinstance(document.get("attempt_count"), bool)
        or not isinstance(document.get("attempt_count"), int)
        or document.get("attempt_count") != len(attempts)
    ):
        raise ContractViolation("affinity placement receipt attempt count is invalid")
    selected_target = document.get("selected_target")
    candidate_digest = document.get("candidate_digest")
    parsed_attempts: list[PlacementAttempt] = []
    attempt_fields = frozenset(
        {
            "attempt",
            "target_id",
            "candidate_digest",
            "decision_digest",
            "command_digest",
            "disposition",
            "reason_code",
            "sink_receipt_digest",
            "placement_id",
            "retryable",
        }
    )
    for raw_attempt in attempts:
        if not isinstance(raw_attempt, Mapping) or set(raw_attempt) != attempt_fields:
            raise ContractViolation("affinity placement receipt attempt shape is invalid")
        try:
            disposition = PlacementDisposition(str(raw_attempt["disposition"]))
        except (TypeError, ValueError) as exc:
            raise ContractViolation("affinity placement attempt disposition is invalid") from exc
        parsed_attempts.append(
            PlacementAttempt(
                attempt=raw_attempt["attempt"],
                target_id=_identifier_value(raw_attempt["target_id"], "target_id"),
                candidate_digest=_digest_value(raw_attempt["candidate_digest"], "candidate_digest"),
                decision_digest=_digest_value(raw_attempt["decision_digest"], "decision_digest"),
                command_digest=_digest_value(raw_attempt["command_digest"], "command_digest"),
                disposition=disposition,
                reason_code=_identifier_value(raw_attempt["reason_code"], "reason_code"),
                sink_receipt_digest=_digest_value(raw_attempt["sink_receipt_digest"], "sink_receipt_digest"),
                placement_id=(
                    None
                    if raw_attempt["placement_id"] is None
                    else _identifier_value(raw_attempt["placement_id"], "placement_id")
                ),
                retryable=raw_attempt["retryable"],
            )
        )

    receipt_digest = _digest_value(document.get("receipt_digest"), "receipt_digest")
    unsigned = {key: value for key, value in document.items() if key != "receipt_digest"}
    if receipt_digest != digest_of(unsigned):
        raise ContractViolation("affinity placement receipt digest is invalid")

    receipt = AffinityPlacementReceipt(
        tenant_id=_identifier_value(document.get("tenant_id"), "tenant_id"),
        project_id=_identifier_value(document.get("project_id"), "project_id"),
        principal_digest=_digest_value(document.get("principal_digest"), "principal_digest"),
        request_id=_identifier_value(document.get("request_id"), "request_id"),
        affinity_key=_digest_value(document.get("affinity_key"), "affinity_key"),
        inventory_digest=_digest_value(document.get("inventory_digest"), "inventory_digest"),
        outcome=outcome,
        selected_target=(
            None if selected_target is None else _identifier_value(selected_target, "selected_target")
        ),
        candidate_digest=(
            None if candidate_digest is None else _digest_value(candidate_digest, "candidate_digest")
        ),
        final_decision_digest=_digest_value(document.get("final_decision_digest"), "final_decision_digest"),
        attempts=tuple(parsed_attempts),
    )

    if receipt_digest != receipt.receipt_digest:
        raise ContractViolation("affinity placement receipt digest is invalid")


def _identifier_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field_name} must be a string")
    return _identifier(value, field_name)


def _digest_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field_name} must be a digest")
    return require_digest(value)


__all__ = [
    "AFFINITY_PLACEMENT_RECEIPT_KIND",
    "AFFINITY_PLACEMENT_SCHEMA_VERSION",
    "AffinityPlacementReceipt",
    "AffinityPlacementResult",
    "AffinityPlacementService",
    "AttestedRegistryInventorySource",
    "PlacementCommand",
    "PlacementDisposition",
    "PlacementOutcome",
    "PlacementSink",
    "PlacementSinkResult",
    "RunnerInventorySnapshot",
    "RunnerInventorySource",
    "verify_affinity_placement_receipt",
]
