# Idempotency

Use a dedicated table; do not use the customer ledger as an idempotency cache.

## Required key

`(tenant_id, operation_type, idempotency_key)`

Store:
- request_hash
- state
- resource_id
- response_json
- started_at
- completed_at
- expires_at
- last_error

## Rules

- same key + same request hash + SUCCEEDED => return stored result.
- same key + different request hash => 409 conflict.
- IN_PROGRESS => reconcile operation-specific external/internal state.
- FAILED retry policy must be explicit.
