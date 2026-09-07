# ADR-0009: Webhook authentication and idempotency

Status: Accepted

## Decision

The control plane verifies GitHub HMAC-SHA-256 over exact raw bytes using constant-time comparison. It then atomically inserts a delivery keyed by GitHub delivery id, stores only a bounded normalized envelope plus payload digest, enqueues downstream work, and returns. Duplicate deliveries are accepted no-ops.

## Consequences

No clone, snapshot, or workspace work runs in the HTTP request. Invalid requests create no durable delivery.
