# API Contract

Base path: `/api/v1`

All mutating requests require verified authentication, tenant membership, `X-Request-Id`, and where appropriate `Idempotency-Key`. Tenant identity is not authorized from a client-controlled tenant header.

## 1. Task APIs

### `POST /tasks`

Creates an immutable task request and performs admission.

Headers:

```text
Authorization: Bearer ...
Idempotency-Key: ...
X-Request-Id: ...
```

Request summary:

```json
{
  "tenant_id": "selected tenant UUID; verified against membership",
  "project_id": "optional UUID",
  "task_type": "PROJECT_GENERATION",
  "title": "Generate ...",
  "priority": "NORMAL",
  "workload_class": "CODE_GENERATION",
  "input": {},
  "input_artifact_ids": [],
  "budget": {
    "max_cost_amount": "25.00",
    "currency": "USD"
  }
}
```

The client may select a tenant, but the server resolves and authorizes membership. The server never treats the value alone as authorization.

Response:

```json
{
  "task_id": "...",
  "state": "ADMITTED",
  "active_slots": 2,
  "maximum_slots": 3,
  "queued_count": 0,
  "admission_reasons": [],
  "links": {}
}
```

Fourth task response remains successful and durable:

```json
{
  "task_id": "...",
  "state": "WAITING_FOR_SLOT",
  "active_slots": 3,
  "maximum_slots": 3,
  "queued_count": 1,
  "queue_position": 1,
  "admission_reasons": ["ACCOUNT_ACTIVE_LIMIT"]
}
```

### `GET /tasks/{taskId}`

Returns authorized current task, run, progress, cost, and artifact summary.

### `GET /tasks`

Filters:

- state;
- project;
- task type;
- created range;
- account (authorized role);
- cost/revenue status;
- pagination.

### `POST /tasks/{taskId}/pause`

Idempotently requests pause. Returns current state and control request ID.

### `POST /tasks/{taskId}/resume`

Validates authorization and moves a paused/manual-recovery task to `WAITING_FOR_SLOT` or performs an approved recovery action.

### `POST /tasks/{taskId}/cancel`

Idempotently requests cancellation and propagates to Temporal/runner.

### `POST /tasks/{taskId}/retry`

Creates a new run or schedules an allowed node retry according to failure policy.

## 2. Progress APIs

### `GET /tasks/{taskId}/events?after_sequence=N&limit=M`

Returns durable ordered task events.

### `GET /tasks/{taskId}/stream`

SSE stream. Supports:

```text
Last-Event-ID: sequence number
```

SSE event:

```text
id: 42
event: NodeProgressed
data: {...}
```

### `GET /tasks/{taskId}/nodes`

Returns node and attempt history.

### `GET /tasks/{taskId}/checkpoints`

Returns authorized checkpoint metadata, not secret content.

### `GET /tasks/{taskId}/logs`

Returns log-segment metadata and signed/authorized retrieval links.

## 3. Concurrency APIs

### `GET /me/task-concurrency`

```json
{
  "account_id": "...",
  "active_slots": 2,
  "maximum_slots": 3,
  "occupied": [
    {"slot_no": 1, "task_id": "...", "tenant_id": "...", "state": "RUNNING"},
    {"slot_no": 2, "task_id": "...", "tenant_id": "...", "state": "PAUSING"}
  ],
  "queued_count": 4
}
```

### `GET /tenants/{tenantId}/runtime-capacity`

Authorized tenant owner/operations view of tenant quota, resource units, queue, budget, and provider gates.

### `PUT /admin/tenants/{tenantId}/runtime-quota`

Platform admin only. May change tenant quotas but may not raise account hard limit above three.

## 4. Artifact APIs

### `POST /tasks/{taskId}/inputs`

Creates upload intent or records an input object manifest.

### `GET /tasks/{taskId}/artifacts`

Returns versioned artifacts and integrity status.

### `GET /artifacts/{artifactId}`

Returns metadata and authorized download/render links.

### `POST /artifacts/{artifactId}/verify`

Recomputes/validates object integrity according to policy.

## 5. Financial APIs

### `GET /tasks/{taskId}/cost`

Returns estimate, reservation, posted actual, final actual, dimensions, `as_of`, and reconciliation status.

### `GET /tasks/{taskId}/financial-summary`

Authorized finance view:

```json
{
  "task_id": "...",
  "reporting_currency": "USD",
  "as_of": "...",
  "cost": {
    "estimated": "12.10",
    "reserved": "15.00",
    "posted_actual": "11.74",
    "final_actual": null,
    "status": "POSTING"
  },
  "revenue": {
    "net_billed": "20.00",
    "recognized": "20.00",
    "collected_cash": "20.00",
    "status": "FINAL"
  },
  "gross_profit": "8.26",
  "gross_margin": "0.4130"
}
```

### `GET /analytics/task-financials`

Filters by tenant, account, project, task type, provider/model, workload, period, basis, currency, and reconciliation state.

### `GET /analytics/task-operations`

Returns throughput, queue, duration, retry, recovery, cancellation, cache, and concurrency metrics.

### `POST /finance/usage-events`

Internal authenticated adapter endpoint. Requires idempotency/provider receipt.

### `POST /finance/revenue-entries`

Authorized billing adapter/finance endpoint.

### `POST /finance/revenue-allocations`

Authorized allocation endpoint with policy version.

## 6. Error contract

```json
{
  "type": "https://errors.elmos.dev/task/account-limit",
  "title": "Task is waiting for an account execution slot",
  "status": 202,
  "code": "ACCOUNT_ACTIVE_LIMIT",
  "detail": "The account already has three active root tasks.",
  "task_id": "...",
  "trace_id": "...",
  "retryable": true,
  "next_action": "WAIT"
}
```

The fourth task is normally a `202` durable queued response, not an error. Hard rejects use:

- `400` invalid request;
- `401` unauthenticated;
- `403` unauthorized tenant/action;
- `404` not found within authorized scope;
- `409` idempotency conflict or stale lease generation;
- `413` request/upload limit;
- `422` unsupported task/checkpoint policy;
- `429` submission queue/budget/provider hard limit where durable queueing is not permitted;
- `503` temporary platform admission outage after task persistence policy is applied.

## 7. Idempotency

- Task create: `(tenant_id, account_id, Idempotency-Key)`.
- Control requests: `(task_id, action, Idempotency-Key)`.
- Runner completion: `(task_run_id, node_key, attempt_no, lease_generation, receipt_id)`.
- Usage: provider receipt ID or internal metering idempotency key.
- Revenue: payment/billing provider object plus kind/version.
- Event transition: `transition_id`.

An idempotency key reused with a different request hash returns `409`.

## 8. Pagination and consistency

List APIs use cursor pagination. Responses identify:

- `as_of`;
- snapshot/event watermark;
- whether financial data is posting/final;
- whether progress is current or reconstructed.

Critical state is strongly consistent with the committed database transaction. UI progress and analytics are eventually consistent.
