"""Industrial-grade Transactional Outbox Dispatcher for event delivery, retries, and DLQ."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from .contracts import SecurityContext
from .storage import ControlPlaneStore

logger = logging.getLogger("elmos_proof_harness.outbox")


@dataclass(frozen=True)
class OutboxMessage:
    tenant_id: str
    project_id: str
    event_id: str
    topic: str
    aggregate_id: str
    payload_json: str
    payload_sha256: str
    created_at: str

    @property
    def payload(self) -> dict[str, Any]:
        try:
            val = json.loads(self.payload_json)
            return val if isinstance(val, dict) else {"data": val}
        except Exception:
            return {"raw": self.payload_json}


class OutboxHandler(Protocol):
    def __call__(self, message: OutboxMessage) -> tuple[bool, str | None]:
        """Process an outbox message. Returns (success, optional error_or_detail_string)."""
        ...


class TransactionalStore(Protocol):
    def transaction(self, context: SecurityContext) -> Any:
        ...

    def record_outbox_delivery(
        self,
        context: SecurityContext,
        *,
        event_id: str,
        destination: str,
        state: str,
        detail: bytes | None = None,
    ) -> str:
        ...


class OutboxDispatcher:
    """Dispatches outbox events from the durable store with idempotency, retries, and audit logging."""

    def __init__(
        self,
        store: TransactionalStore,
        context: SecurityContext,
        default_destination: str = "internal-bus",
    ) -> None:
        self._store = store
        self._context = context
        self._default_destination = default_destination
        self._handlers: dict[str, list[OutboxHandler]] = {}
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def register_handler(self, topic: str, handler: OutboxHandler) -> None:
        with self._lock:
            if topic not in self._handlers:
                self._handlers[topic] = []
            self._handlers[topic].append(handler)

    def fetch_pending(self, limit: int = 50) -> list[OutboxMessage]:
        """Fetch outbox events that have not been successfully delivered or marked DEAD_LETTER."""
        messages: list[OutboxMessage] = []
        with self._store.transaction(self._context) as cursor:
            # Query outbox_events that lack a successful delivery or dead-letter in outbox_deliveries
            query = (
                "SELECT e.tenant_id, e.project_id, e.event_id, e.topic, e.aggregate_id, "
                "e.payload_json, e.payload_sha256, e.created_at "
                "FROM outbox_events e "
                "WHERE e.tenant_id = ? AND e.project_id = ? "
                "AND NOT EXISTS ("
                "    SELECT 1 FROM outbox_deliveries d "
                "    WHERE d.tenant_id = e.tenant_id AND d.project_id = e.project_id "
                "    AND d.event_id = e.event_id AND d.state IN ('DELIVERED', 'DEAD_LETTER')"
                ") "
                "ORDER BY e.created_at ASC LIMIT ?"
            )
            # Adapt query placeholder for PostgreSQL if backend is Postgres
            if getattr(self._store, "backend_name", None) == "PostgreSQL":
                query = query.replace("?", "%s")

            cursor.execute(query, (self._context.tenant_id, self._context.project_id, limit))
            rows = cursor.fetchall()
            for r in rows:
                messages.append(
                    OutboxMessage(
                        tenant_id=str(r["tenant_id"]),
                        project_id=str(r["project_id"]),
                        event_id=str(r["event_id"]),
                        topic=str(r["topic"]),
                        aggregate_id=str(r["aggregate_id"]),
                        payload_json=str(r["payload_json"]),
                        payload_sha256=str(r["payload_sha256"]),
                        created_at=str(r["created_at"]),
                    )
                )
        return messages

    def dispatch_message(
        self,
        message: OutboxMessage,
        max_attempts: int = 3,
        destination: str | None = None,
    ) -> str:
        """Dispatch a single outbox message to registered handlers and record delivery."""
        dest = destination or self._default_destination
        handlers = self._handlers.get(message.topic, []) + self._handlers.get("*", [])

        if not handlers:
            # No handlers registered for this topic; mark as delivered (no-op dispatch)
            detail = f"No handlers registered for topic {message.topic}".encode("utf-8")
            return self._store.record_outbox_delivery(
                self._context,
                event_id=message.event_id,
                destination=dest,
                state="DELIVERED",
                detail=detail,
            )

        all_success = True
        last_error: str | None = None

        for handler in handlers:
            success = False
            for attempt in range(1, max_attempts + 1):
                try:
                    ok, err = handler(message)
                    if ok:
                        success = True
                        break
                    else:
                        last_error = err or f"Handler returned failure on attempt {attempt}"
                except Exception as exc:
                    last_error = f"Exception on attempt {attempt}: {exc}"
                    logger.warning("Outbox handler failed attempt %d: %s", attempt, exc)
                time.sleep(0.01 * attempt)

            if not success:
                all_success = False
                break

        state = "DELIVERED" if all_success else "DEAD_LETTER"
        detail_bytes = (
            f"Delivered to {len(handlers)} handler(s)".encode("utf-8")
            if all_success
            else f"Failed after {max_attempts} attempts: {last_error}".encode("utf-8")
        )

        return self._store.record_outbox_delivery(
            self._context,
            event_id=message.event_id,
            destination=dest,
            state=state,
            detail=detail_bytes,
        )

    def dispatch_batch(self, limit: int = 50, max_attempts: int = 3) -> int:
        """Fetch and dispatch a batch of pending events. Returns count of dispatched events."""
        pending = self.fetch_pending(limit=limit)
        dispatched = 0
        for msg in pending:
            try:
                self.dispatch_message(msg, max_attempts=max_attempts)
                dispatched += 1
            except Exception as exc:
                logger.error("Failed to dispatch outbox message %s: %s", msg.event_id, exc)
        return dispatched

    def start_worker(self, poll_interval_seconds: float = 0.5, batch_size: int = 50) -> None:
        """Start a background daemon thread to continuously poll and dispatch outbox messages."""
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return
            self._stop_event.clear()

            def _run() -> None:
                while not self._stop_event.is_set():
                    try:
                        count = self.dispatch_batch(limit=batch_size)
                        if count == 0:
                            self._stop_event.wait(poll_interval_seconds)
                    except Exception as exc:
                        logger.error("Outbox worker loop error: %s", exc)
                        self._stop_event.wait(poll_interval_seconds)

            self._worker_thread = threading.Thread(target=_run, daemon=True, name="outbox-worker")
            self._worker_thread.start()

    def stop_worker(self, timeout: float = 5.0) -> None:
        """Stop background outbox worker."""
        with self._lock:
            self._stop_event.set()
            if self._worker_thread is not None:
                self._worker_thread.join(timeout=timeout)
                self._worker_thread = None
