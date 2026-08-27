# API and Event Semantics

## Command semantics

Mutating requests require:

- authenticated tenant/account/actor;
- `Idempotency-Key`;
- `traceparent`;
- request schema validation;
- optimistic version or fencing token where applicable;
- credit reservation for proof execution.

A 202 response means durable acceptance, not proof success. Success is represented by a terminal proof run and immutable result/artifacts.

## Error semantics

Use RFC problem details. Distinguish:

- invalid specification;
- unsupported semantic feature;
- invalid state transition;
- account concurrency limit;
- insufficient credit;
- stale fencing token;
- evidence digest conflict;
- policy denial;
- infrastructure unavailable.

## Events

Proof events are at-least-once and carry unique event IDs. Consumers deduplicate. Gate decisions are derived from database state and can be rebuilt; events are notifications, not the sole source of truth.

## Pagination and filtering

Artifact and run listings use opaque cursors. Filters are tenant-scoped and bounded. Formula/body search is an explicit high-privilege feature because it may expose source content.

## Versioning

Backward-compatible fields are additive. Changes to proof status, assurance semantics, cache dimensions or gate policy are versioned and require replay analysis.
