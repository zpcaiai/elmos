"""Runtime-owned worker for bounded knowledge rebuilds and outbox delivery.

The worker deliberately has no request-facing command surface.  Its tenant scope,
package scope, authority token, executor identity, transport, and work bounds are
all injected by trusted runtime composition.  Repository or intake content can
therefore neither select a command nor replace the delivery transport.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from .canonical import (
    canonical_digest,
    canonical_json,
    new_id,
    normalize_sha256,
    require_resource_id,
    sha256_bytes,
)
from .errors import IntakeError, IntegrityError, ValidationError
from .models import TenantContext
from .persistent_knowledge import PersistentKnowledgeStore


class KnowledgeOutboxTransport(Protocol):
    """Trusted runtime transport with provider-side idempotency support."""

    def deliver(
        self,
        event: Mapping[str, Any],
        *,
        idempotency_key: str,
    ) -> Mapping[str, Any]: ...


class KnowledgeWorker:
    """Execute one bounded unit of runtime-owned persistent-knowledge work."""

    _REBUILD_STATES = ("RUNNING", "FAILED", "PENDING")
    _REBUILD_TARGETS = frozenset({"content-index", "project-memory"})
    _OUTBOX_EVENT_KEYS = frozenset(
        {
            "event_id",
            "event_type",
            "aggregate_id",
            "payload",
            "payload_digest",
            "idempotency_key",
            "occurred_at",
            "published_at",
            "publication_receipt",
        }
    )
    _OUTBOX_CLAIM_KEYS = _OUTBOX_EVENT_KEYS | frozenset(
        {
            "delivery_phase",
            "delivery_attempt",
            "claim_token_digest",
            "executor_id",
            "lease_expires_at",
        }
    )
    _TRANSPORT_RECEIPT_KEYS = frozenset(
        {"event_id", "payload_digest", "delivery_state", "provider_message_id"}
    )

    def __init__(
        self,
        knowledge: PersistentKnowledgeStore,
        *,
        context: TenantContext,
        branch: str,
        package_version: str,
        worker_capability: object,
        transport: KnowledgeOutboxTransport,
        executor_id: str,
        max_rebuild_targets: int = 2,
        max_outbox_events: int = 100,
        delivery_lease_seconds: int = 300,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(knowledge, PersistentKnowledgeStore):
            raise TypeError("KnowledgeWorker requires PersistentKnowledgeStore")
        if not isinstance(context, TenantContext):
            raise TypeError("KnowledgeWorker requires TenantContext")
        knowledge.require_worker_admin(
            context,
            worker_capability=worker_capability,
        )
        deliver = getattr(transport, "deliver", None)
        if not callable(deliver):
            raise ValidationError("KNOWLEDGE_WORKER_TRANSPORT_INVALID")
        self._knowledge = knowledge
        self._context = context
        self._branch = self._bounded_text(branch, "branch", 256)
        self._package_version = self._bounded_text(
            package_version,
            "package_version",
            128,
        )
        self._worker_capability = worker_capability
        self._transport = transport
        self._executor_id = self._bounded_text(executor_id, "executor_id", 256)
        self._max_rebuild_targets = self._bounded_integer(
            max_rebuild_targets,
            "max_rebuild_targets",
            maximum=2,
        )
        self._max_outbox_events = self._bounded_integer(
            max_outbox_events,
            "max_outbox_events",
            maximum=100,
        )
        self._delivery_lease_seconds = self._bounded_integer(
            delivery_lease_seconds,
            "delivery_lease_seconds",
            maximum=3_600,
        )
        if clock is not None and not callable(clock):
            raise ValidationError("KNOWLEDGE_WORKER_CLOCK_INVALID")
        self._clock = clock or (lambda: datetime.now(UTC))

    @staticmethod
    def _bounded_text(value: object, field: str, maximum: int) -> str:
        if not isinstance(value, str):
            raise ValidationError("KNOWLEDGE_WORKER_CONFIGURATION_INVALID", field)
        try:
            encoded = value.encode("utf-8", errors="strict")
        except UnicodeEncodeError as error:
            raise ValidationError("KNOWLEDGE_WORKER_CONFIGURATION_INVALID", field) from error
        if (
            not value
            or len(encoded) > maximum
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValidationError("KNOWLEDGE_WORKER_CONFIGURATION_INVALID", field)
        return value

    @staticmethod
    def _bounded_integer(value: object, field: str, *, maximum: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValidationError("KNOWLEDGE_WORKER_CONFIGURATION_INVALID", field)
        return value

    @staticmethod
    def _nonnegative_integer(value: object, field: str, *, minimum: int = 0) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise IntegrityError("KNOWLEDGE_WORKER_STORED_INTEGER_INVALID", details={"field": field})
        return value

    def _completed_at(self) -> str:
        try:
            value = self._clock()
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError("timezone-aware datetime required")
            return value.astimezone(UTC).replace(microsecond=0).isoformat()
        except Exception as error:
            raise IntegrityError("KNOWLEDGE_WORKER_CLOCK_INVALID") from error

    def _worker_receipt(self, binding: Mapping[str, Any]) -> dict[str, Any]:
        body = {
            "schema_version": "1.0.0",
            **dict(binding),
            "executor_id": self._executor_id,
            "completed_at": self._completed_at(),
        }
        return {**body, "receipt_digest": canonical_digest(body)}

    @staticmethod
    def _idempotency_key(purpose: str, binding: Mapping[str, Any]) -> str:
        return f"knowledge-worker:{purpose}:{canonical_digest(binding)}"

    @staticmethod
    def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
        decoded = json.loads(canonical_json(value))
        if not isinstance(decoded, dict):
            raise IntegrityError("KNOWLEDGE_WORKER_CANONICALIZATION_FAILED")
        return decoded

    def _select_rebuild_jobs(self) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        selected_targets: set[str] = set()
        for status in self._REBUILD_STATES:
            jobs = self._knowledge.list_rebuild_jobs(
                self._context,
                branch=self._branch,
                package_version=self._package_version,
                status=status,
                limit=100,
            )
            for job in jobs:
                target = job.get("target")
                if target not in self._REBUILD_TARGETS:
                    raise IntegrityError("KNOWLEDGE_REBUILD_STORED_TARGET_INVALID")
                if target in selected_targets:
                    continue
                rebuild_id = job.get("rebuild_id")
                cause_digest = job.get("cause_digest")
                try:
                    require_resource_id(rebuild_id, "rebuild_id")
                    normalize_sha256(cause_digest)
                except (TypeError, ValueError, ValidationError) as error:
                    raise IntegrityError("KNOWLEDGE_REBUILD_STORED_JOB_INVALID") from error
                attempt = job.get("attempt")
                if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
                    raise IntegrityError("KNOWLEDGE_REBUILD_STORED_JOB_INVALID")
                selected.append(dict(job))
                selected_targets.add(str(target))
                if len(selected) >= self._max_rebuild_targets:
                    return selected
        return selected

    @staticmethod
    def _failure_code(error: Exception) -> str:
        candidate = error.code if isinstance(error, IntakeError) else "KNOWLEDGE_REBUILD_FAILED"
        if isinstance(candidate, str) and candidate:
            try:
                encoded = candidate.encode("utf-8", errors="strict")
            except UnicodeEncodeError:
                encoded = b""
            if (
                encoded
                and len(encoded) <= 128
                and all(ord(character) >= 32 and ord(character) != 127 for character in candidate)
            ):
                return candidate
        return "KNOWLEDGE_REBUILD_FAILED"

    def _run_rebuild(self, job: Mapping[str, Any]) -> dict[str, Any]:
        rebuild_id = str(job["rebuild_id"])
        cause_digest = str(job["cause_digest"])
        target = str(job["target"])
        from_state = str(job["status"])
        attempt = int(job["attempt"])
        if from_state != "RUNNING":
            transition_binding = {
                "rebuild_id": rebuild_id,
                "cause_digest": cause_digest,
                "from_state": from_state,
                "target_state": "RUNNING",
                "failure_code": None,
            }
            transition = self._knowledge.transition_rebuild(
                self._context,
                rebuild_id=rebuild_id,
                target_state="RUNNING",
                idempotency_key=self._idempotency_key(
                    "rebuild-start",
                    {
                        "rebuild_id": rebuild_id,
                        "from_state": from_state,
                        "attempt": attempt,
                    },
                ),
                worker_capability=self._worker_capability,
                execution_receipt=self._worker_receipt(transition_binding),
            )
            if transition.get("status") != "RUNNING":
                raise IntegrityError("KNOWLEDGE_REBUILD_TRANSITION_EVIDENCE_INVALID")
            transition_attempt = transition.get("attempt")
            if (
                isinstance(transition_attempt, bool)
                or not isinstance(transition_attempt, int)
                or transition_attempt <= attempt
            ):
                raise IntegrityError("KNOWLEDGE_REBUILD_TRANSITION_EVIDENCE_INVALID")
            attempt = transition_attempt

        rebuild_binding = {
            "rebuild_id": rebuild_id,
            "cause_digest": cause_digest,
            "target": target,
            "attempt": attempt,
        }
        try:
            rebuilt = self._knowledge.rebuild_lexical_index(
                self._context,
                branch=self._branch,
                package_version=self._package_version,
                target=target,
                idempotency_key=self._idempotency_key("rebuild-execute", rebuild_binding),
                worker_capability=self._worker_capability,
            )
        except Exception as error:
            failure_code = self._failure_code(error)
            failure_binding = {
                "rebuild_id": rebuild_id,
                "cause_digest": cause_digest,
                "from_state": "RUNNING",
                "target_state": "FAILED",
                "failure_code": failure_code,
            }
            try:
                self._knowledge.transition_rebuild(
                    self._context,
                    rebuild_id=rebuild_id,
                    target_state="FAILED",
                    idempotency_key=self._idempotency_key(
                        "rebuild-failed",
                        {
                            "rebuild_id": rebuild_id,
                            "attempt": attempt,
                            "failure_code": failure_code,
                        },
                    ),
                    worker_capability=self._worker_capability,
                    execution_receipt=self._worker_receipt(failure_binding),
                    failure_code=failure_code,
                )
            except Exception as transition_error:
                raise IntegrityError(
                    "KNOWLEDGE_REBUILD_FAILURE_RECORDING_FAILED",
                    retryable=True,
                ) from transition_error
            if isinstance(error, IntakeError):
                raise
            raise IntegrityError("KNOWLEDGE_REBUILD_EXECUTION_FAILED") from error

        if not isinstance(rebuilt, Mapping):
            raise IntegrityError("KNOWLEDGE_REBUILD_COMPLETION_EVIDENCE_INVALID")
        try:
            rebuilt_digest = normalize_sha256(rebuilt.get("rebuilt_digest"))
            event_id = require_resource_id(rebuilt.get("event_id"), "event_id")
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("KNOWLEDGE_REBUILD_COMPLETION_EVIDENCE_INVALID") from error
        if rebuilt.get("target") != target or rebuilt.get("rebuild_state") != "SUCCEEDED":
            raise IntegrityError("KNOWLEDGE_REBUILD_COMPLETION_EVIDENCE_INVALID")
        record_count = self._nonnegative_integer(rebuilt.get("record_count"), "record_count")
        term_count = self._nonnegative_integer(rebuilt.get("term_count"), "term_count")
        completed_job_count = self._nonnegative_integer(
            rebuilt.get("completed_job_count"),
            "completed_job_count",
            minimum=1,
        )
        return {
            "rebuild_id": rebuild_id,
            "target": target,
            "attempt": attempt,
            "record_count": record_count,
            "term_count": term_count,
            "completed_job_count": completed_job_count,
            "rebuilt_digest": rebuilt_digest,
            "event_id": event_id,
        }

    def _validate_transport_receipt(
        self,
        value: Mapping[str, Any],
        *,
        event_id: str,
        payload_digest: str,
    ) -> dict[str, Any]:
        if not isinstance(value, Mapping) or set(value) != self._TRANSPORT_RECEIPT_KEYS:
            raise IntegrityError("KNOWLEDGE_OUTBOX_TRANSPORT_RECEIPT_INVALID")
        if (
            value.get("event_id") != event_id
            or value.get("payload_digest") != payload_digest
            or value.get("delivery_state") != "DELIVERED"
        ):
            raise IntegrityError("KNOWLEDGE_OUTBOX_TRANSPORT_RECEIPT_BINDING_MISMATCH")
        provider_message_id = self._bounded_text(
            value.get("provider_message_id"),
            "provider_message_id",
            512,
        )
        return {
            "event_id": event_id,
            "payload_digest": payload_digest,
            "delivery_state": "DELIVERED",
            "provider_message_id": provider_message_id,
        }

    def _record_unknown(
        self,
        *,
        event_id: str,
        claim_token: str,
        error_code: str,
    ) -> dict[str, Any]:
        try:
            return self._knowledge.mark_outbox_unknown(
                self._context,
                event_id,
                worker_capability=self._worker_capability,
                claim_token=claim_token,
                error_code=error_code,
            )
        except Exception as error:
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_UNKNOWN_RECORDING_FAILED",
                retryable=False,
            ) from error

    def _deliver_outbox_event(
        self,
        event: Mapping[str, Any],
        *,
        claim_token: str,
    ) -> dict[str, Any]:
        if not isinstance(event, Mapping) or set(event) != self._OUTBOX_CLAIM_KEYS:
            raise IntegrityError("KNOWLEDGE_OUTBOX_STORED_EVENT_INVALID")
        if event.get("published_at") is not None or event.get("publication_receipt") is not None:
            raise IntegrityError("KNOWLEDGE_OUTBOX_STORED_EVENT_INVALID")
        try:
            event_id = require_resource_id(event.get("event_id"), "event_id")
            require_resource_id(event.get("aggregate_id"), "aggregate_id")
            payload_digest = normalize_sha256(event.get("payload_digest"))
            self._bounded_text(event.get("event_type"), "event_type", 128)
            self._bounded_text(event.get("idempotency_key"), "event_idempotency_key", 512)
            occurred_at_value = event.get("occurred_at")
            if not isinstance(occurred_at_value, str):
                raise ValueError("outbox timestamp must be a string")
            occurred_at = datetime.fromisoformat(occurred_at_value)
            if occurred_at.tzinfo is None:
                raise ValueError("outbox timestamp must include a timezone")
            delivery_attempt = event.get("delivery_attempt")
            if (
                event.get("delivery_phase") != "CLAIMED"
                or isinstance(delivery_attempt, bool)
                or not isinstance(delivery_attempt, int)
                or not 1 <= delivery_attempt <= 10
                or event.get("executor_id") != self._executor_id
            ):
                raise ValueError("outbox claim binding is invalid")
            claim_token_digest = normalize_sha256(event.get("claim_token_digest"))
            if claim_token_digest != sha256_bytes(claim_token.encode("utf-8")):
                raise ValueError("outbox claim fence is invalid")
            lease_value = event.get("lease_expires_at")
            if not isinstance(lease_value, str):
                raise ValueError("outbox lease timestamp must be a string")
            lease_expires_at = datetime.fromisoformat(lease_value)
            if lease_expires_at.tzinfo is None:
                raise ValueError("outbox lease timestamp must include a timezone")
        except (TypeError, ValueError, ValidationError) as error:
            raise IntegrityError("KNOWLEDGE_OUTBOX_STORED_EVENT_INVALID") from error
        if not isinstance(event.get("payload"), Mapping):
            raise IntegrityError("KNOWLEDGE_OUTBOX_STORED_EVENT_INVALID")
        if canonical_digest(event["payload"]) != payload_digest:
            raise IntegrityError("KNOWLEDGE_OUTBOX_STORED_PAYLOAD_MISMATCH")
        dispatch = self._knowledge.mark_outbox_dispatching(
            self._context,
            event_id,
            worker_capability=self._worker_capability,
            claim_token=claim_token,
        )
        if (
            dispatch.get("delivery_phase") != "DISPATCHING"
            or dispatch.get("delivery_attempt") != delivery_attempt
            or dispatch.get("claim_token_digest") != claim_token_digest
            or dispatch.get("executor_id") != self._executor_id
        ):
            raise IntegrityError("KNOWLEDGE_OUTBOX_DISPATCH_EVIDENCE_INVALID")
        transport_key = self._idempotency_key(
            "outbox-deliver",
            {"event_id": event_id, "payload_digest": payload_digest},
        )
        transport_event = self._plain_mapping(
            {key: event[key] for key in self._OUTBOX_EVENT_KEYS}
        )
        try:
            transport_result = self._transport.deliver(
                transport_event,
                idempotency_key=transport_key,
            )
        except Exception as error:
            self._record_unknown(
                event_id=event_id,
                claim_token=claim_token,
                error_code="KNOWLEDGE_OUTBOX_TRANSPORT_OUTCOME_UNKNOWN",
            )
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_TRANSPORT_OUTCOME_UNKNOWN",
                retryable=False,
            ) from error
        try:
            transport_receipt = self._validate_transport_receipt(
                transport_result,
                event_id=event_id,
                payload_digest=payload_digest,
            )
        except (IntegrityError, ValidationError) as error:
            self._record_unknown(
                event_id=event_id,
                claim_token=claim_token,
                error_code="KNOWLEDGE_OUTBOX_TRANSPORT_EVIDENCE_INVALID",
            )
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_TRANSPORT_EVIDENCE_INVALID",
                retryable=False,
            ) from error
        transport_receipt_digest = canonical_digest(transport_receipt)
        binding = {
            "tenant_id": self._context.tenant_id,
            "project_id": self._context.project_id,
            "actor_id": self._context.actor_id,
            "event_id": event_id,
            "event_type": event["event_type"],
            "aggregate_id": event["aggregate_id"],
            "payload_digest": payload_digest,
            "delivery_state": "DELIVERED",
            "provider_message_id": transport_receipt["provider_message_id"],
            "attempt": delivery_attempt,
            "claim_token_digest": claim_token_digest,
            "transport_receipt_digest": transport_receipt_digest,
        }
        delivery_receipt = self._worker_receipt(binding)
        try:
            publication = self._knowledge.mark_outbox_published(
                self._context,
                event_id,
                worker_capability=self._worker_capability,
                delivery_receipt=delivery_receipt,
                claim_token=claim_token,
                transport_receipt=transport_receipt,
            )
        except Exception as error:
            unknown = self._record_unknown(
                event_id=event_id,
                claim_token=claim_token,
                error_code="KNOWLEDGE_OUTBOX_PUBLICATION_OUTCOME_UNKNOWN",
            )
            if unknown.get("delivery_phase") == "PUBLISHED":
                return {
                    "event_id": event_id,
                    "provider_message_id": transport_receipt["provider_message_id"],
                    "delivery_receipt_digest": delivery_receipt["receipt_digest"],
                    "published_at": unknown.get("published_at"),
                }
            raise IntegrityError(
                "KNOWLEDGE_OUTBOX_PUBLICATION_OUTCOME_UNKNOWN",
                retryable=False,
            ) from error
        if publication.get("delivery_receipt_digest") != delivery_receipt["receipt_digest"]:
            raise IntegrityError("KNOWLEDGE_OUTBOX_PUBLICATION_EVIDENCE_INVALID")
        published_at = publication.get("published_at")
        try:
            if not isinstance(published_at, str):
                raise ValueError("publication timestamp must be a string")
            parsed_published_at = datetime.fromisoformat(published_at)
            if parsed_published_at.tzinfo is None:
                raise ValueError("publication timestamp must include a timezone")
        except ValueError as error:
            raise IntegrityError("KNOWLEDGE_OUTBOX_PUBLICATION_EVIDENCE_INVALID") from error
        return {
            "event_id": event_id,
            "provider_message_id": transport_receipt["provider_message_id"],
            "delivery_receipt_digest": delivery_receipt["receipt_digest"],
            "published_at": published_at,
        }

    def reconcile_outbox_event(
        self,
        event_id: str,
        reconciliation_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Apply trusted provider reconciliation without re-running the effect."""

        self._knowledge.require_worker_admin(
            self._context,
            worker_capability=self._worker_capability,
        )
        event_id = require_resource_id(event_id, "event_id")
        state = self._knowledge.outbox_delivery_state(self._context, event_id)
        verified = self._knowledge._reconciliation_receipt(
            self._context,
            state,
            reconciliation_receipt,
        )
        reconciliation_digest = canonical_digest(verified)
        binding = {
            "tenant_id": self._context.tenant_id,
            "project_id": self._context.project_id,
            "actor_id": self._context.actor_id,
            "event_id": state["event_id"],
            "event_type": state["event_type"],
            "aggregate_id": state["aggregate_id"],
            "payload_digest": state["payload_digest"],
            "delivery_state": verified["delivery_state"],
            "provider_message_id": verified["provider_message_id"],
            "attempt": state["delivery_attempt"],
            "reconciliation_receipt_digest": reconciliation_digest,
            "from_phase": "UNKNOWN",
        }
        result = self._knowledge.reconcile_outbox_delivery(
            self._context,
            event_id,
            worker_capability=self._worker_capability,
            reconciliation_receipt=verified,
            execution_receipt=self._worker_receipt(binding),
        )
        if (
            result.get("event_id") != event_id
            or result.get("reconciliation_state") != verified["delivery_state"]
        ):
            raise IntegrityError("KNOWLEDGE_OUTBOX_RECONCILIATION_EVIDENCE_INVALID")
        return result

    def run_once(self) -> dict[str, Any]:
        """Run only the work selected by the trusted construction-time scope."""

        self._knowledge.require_worker_admin(
            self._context,
            worker_capability=self._worker_capability,
        )
        rebuild_results = [self._run_rebuild(job) for job in self._select_rebuild_jobs()]
        publication_results: list[dict[str, Any]] = []
        for _index in range(self._max_outbox_events):
            claim_token = new_id("knowledge-claim")
            event = self._knowledge.claim_next_outbox_event(
                self._context,
                worker_capability=self._worker_capability,
                claim_token=claim_token,
                executor_id=self._executor_id,
                lease_seconds=self._delivery_lease_seconds,
            )
            if event is None:
                break
            publication_results.append(
                self._deliver_outbox_event(event, claim_token=claim_token)
            )
        body = {
            "schema_version": "1.0.0",
            "state": "SUCCEEDED" if rebuild_results or publication_results else "IDLE",
            "tenant_id": self._context.tenant_id,
            "project_id": self._context.project_id,
            "actor_id": self._context.actor_id,
            "branch": self._branch,
            "package_version": self._package_version,
            "executor_id": self._executor_id,
            "max_rebuild_targets": self._max_rebuild_targets,
            "max_outbox_events": self._max_outbox_events,
            "delivery_lease_seconds": self._delivery_lease_seconds,
            "rebuild_results": rebuild_results,
            "publication_results": publication_results,
            "completed_at": self._completed_at(),
        }
        return {**body, "receipt_digest": canonical_digest(body)}
