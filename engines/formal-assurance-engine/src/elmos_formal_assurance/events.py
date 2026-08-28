from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .canonical import canonical_json, digest_value, validate_digest
from .contracts import Scope
from .store import StateStore


class EventDeliveryError(RuntimeError):
    """Raised when an event publisher cannot provide a bound receipt."""


class EventPublisher(Protocol):
    """Least-privileged adapter boundary for Kafka/NATS/Redpanda publishers.

    Implementations must use ``event_id`` as their provider idempotency key and
    return a SHA-256 receipt bound to the provider acknowledgement.  This
    protocol deliberately promises at-least-once delivery plus reconciliation,
    never exactly-once delivery.
    """

    def publish(self, *, topic: str, event: dict[str, Any], event_id: str) -> str: ...


@dataclass(frozen=True, slots=True)
class OutboxDeliveryResult:
    attempted: int
    published: int
    failed: int
    dead: int
    event_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "published": self.published,
            "failed": self.failed,
            "dead": self.dead,
            "eventIds": list(self.event_ids),
            "deliverySemantics": "AT_LEAST_ONCE_WITH_IDEMPOTENCY_AND_RECONCILIATION",
        }


class OutboxDispatcher:
    """Dispatch transactional events without coupling state commits to a broker."""

    def __init__(
        self,
        store: StateStore,
        publisher: EventPublisher,
        *,
        max_attempts: int = 10,
    ) -> None:
        if (
            not isinstance(max_attempts, int)
            or isinstance(max_attempts, bool)
            or not 1 <= max_attempts <= 100
        ):
            raise ValueError("max_attempts must be between 1 and 100")
        self.store = store
        self.publisher = publisher
        self.max_attempts = max_attempts

    def dispatch(self, scope: Scope, *, limit: int = 100) -> OutboxDeliveryResult:
        pending = self.store.pending_outbox(scope, limit=limit)
        published = failed = dead = 0
        event_ids: list[str] = []
        for item in pending:
            event_id = validate_digest(item["eventId"], "eventId")
            event = item["event"]
            if not isinstance(event, dict):
                raise EventDeliveryError("outbox event must be an object")
            if event.get("eventId") != event_id:
                raise EventDeliveryError("outbox event identity mismatch")
            if (
                digest_value(
                    {
                        "tenantId": event.get("tenantId"),
                        "aggregateType": event.get("aggregateType"),
                        "aggregateId": event.get("aggregateId"),
                        "sequence": event.get("sequence"),
                        "eventHash": event.get("eventHash"),
                    }
                )
                != event_id
            ):
                raise EventDeliveryError("outbox event digest mismatch")
            message = event.get("message")
            if not isinstance(message, dict):
                raise EventDeliveryError("outbox event message must be an object")
            self._validate_message(str(item["topic"]), message, event_id)
            try:
                receipt = self.publisher.publish(
                    topic=str(item["topic"]), event=message, event_id=event_id
                )
                receipt = validate_digest(receipt, "deliveryReceipt")
                self.store.mark_outbox_published(
                    scope, event_id, delivery_receipt=receipt
                )
                published += 1
            except Exception as exc:  # publisher implementations are untrusted adapters
                failure = self.store.mark_outbox_failed(
                    scope,
                    event_id,
                    error=f"{type(exc).__name__}: {exc}",
                    max_attempts=self.max_attempts,
                )
                failed += 1
                if failure["state"] == "DEAD":
                    dead += 1
            event_ids.append(event_id)
        return OutboxDeliveryResult(
            attempted=len(pending),
            published=published,
            failed=failed,
            dead=dead,
            event_ids=tuple(event_ids),
        )

    @staticmethod
    def _validate_message(topic: str, message: dict[str, Any], event_id: str) -> None:
        if topic == "proofEvents":
            required = {
                "eventId",
                "eventType",
                "tenantId",
                "aggregateId",
                "occurredAt",
            }
            if not required.issubset(message) or message.get("eventId") != event_id:
                raise EventDeliveryError("proof event violates the AsyncAPI contract")
            return
        if topic == "driftEvents":
            required = {"dependencyKind", "dependencyId", "oldHash", "newHash"}
            if set(message) != required:
                raise EventDeliveryError("drift event violates the AsyncAPI contract")
            validate_digest(message.get("oldHash"), "driftEvent.oldHash")
            validate_digest(message.get("newHash"), "driftEvent.newHash")
            return
        if topic == "gateEvents":
            required = {
                "id",
                "tenant",
                "subjectId",
                "gate",
                "decision",
                "policyRevision",
                "evaluatedAt",
                "blockingReasons",
                "evidenceHash",
            }
            if set(message) - (required | {"expiresAt"}) or not required.issubset(
                message
            ):
                raise EventDeliveryError("gate event violates the AsyncAPI contract")
            validate_digest(message.get("evidenceHash"), "gateEvent.evidenceHash")
            return
        raise EventDeliveryError(f"unknown Formal Assurance event topic: {topic}")


class DigestReceiptPublisher:
    """Deterministic in-process publisher for local replay and tests only."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish(self, *, topic: str, event: dict[str, Any], event_id: str) -> str:
        record = {
            "topic": topic,
            "eventId": event_id,
            "payloadDigest": digest_value(event),
            "payloadSize": len(canonical_json(event)),
        }
        self.events.append(record)
        return digest_value(record)


__all__ = [
    "DigestReceiptPublisher",
    "EventDeliveryError",
    "EventPublisher",
    "OutboxDeliveryResult",
    "OutboxDispatcher",
]
