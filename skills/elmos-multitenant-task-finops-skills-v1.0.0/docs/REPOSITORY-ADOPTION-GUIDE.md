# Repository Adoption Guide

## 1. Goal

Apply this Skills package to an existing Elmos repository without assuming the repository uses the exact sample package layout or technology versions.

## 2. Discovery pass

Locate and classify:

| Area | Evidence to collect |
|---|---|
| Identity | OIDC/JWT validation, account model, tenant membership, service principals |
| API | task creation, status, pause/resume/cancel/retry, SSE/WebSocket endpoints |
| Database | task tables, migrations, runtime roles, RLS, connection-pool tenant context |
| Workflow | Temporal namespaces, task queues, workflow IDs, signals, updates, activities |
| Runner | lease/heartbeat/renew/complete/cancel, sandbox and workload identity |
| Storage | input/output/log/checkpoint ownership, encryption and retention |
| Events | outbox, broker, event versioning, consumer deduplication |
| Model gateway | request IDs, usage receipts, token categories, price source |
| Billing | wallet/subscription/project billing, payment events, refunds, recognition |
| Analytics | current dashboards, dimensions, currency basis, `as_of`, rebuild path |
| Observability | trace propagation, queue age, stuck workflow, lease expiry, budget alerts |

Produce `gap-analysis.json` with `existing`, `missing`, `conflicting`, `reusable`, and `unknown` classifications.

## 3. Contract freeze

Before implementation, freeze and version:

- task and node state machines;
- slot-consuming states;
- account-wide three-slot rule;
- API and event payloads;
- Temporal workflow ID and search attributes;
- error and recovery classifications;
- object manifest and retention rules;
- usage dimensions and price-book semantics;
- revenue kinds, allocation, recognition, and reporting currency;
- permission and RLS matrix.

Any incompatible change requires a migration strategy and explicit version transition.

## 4. Minimal production-shaped slice

Implement this path first:

```text
verified identity
→ idempotent task create
→ durable WAITING_FOR_SLOT
→ atomic slot claim
→ deterministic Temporal start
→ one real workload node
→ ordered progress event
→ durable checkpoint
→ immutable artifact
→ usage event and cost
→ revenue allocation
→ task financial summary
→ terminal state and slot release
```

The slice must include duplicate submission, API restart, Worker loss, cancellation, provider timeout, and ledger duplicate tests.

## 5. Schema adoption

The SQL under `sql/` is a reference migration, not a blind copy command. Adapt foreign keys to the repository's canonical tenant/account/project tables while preserving:

- global `(account_id, slot_no)` primary key with exactly three rows;
- composite tenant ownership constraints on task-related data;
- immutable transition and financial idempotency keys;
- lease generation/fencing;
- FORCE RLS and non-owner runtime roles;
- append-only task, usage, and revenue history;
- rebuildable summaries.

Run migrations with a dedicated owner role. Run applications with non-owner, non-superuser, `NOBYPASSRLS` roles.

## 6. Temporal adoption

- Generate deterministic workflow IDs before start.
- Use outbox starter, compare-and-set state, or Update-with-Start to remove DB/Temporal double-write races.
- Use versioned data records and a Data Converter, not hand-built JSON strings.
- Model business failures as non-retryable application failures where appropriate.
- Use Signals/Updates for pause, resume, cancel, approval, and progress interaction.
- Use Async Activity Completion or runner callbacks for long external work.
- Use Continue-As-New and Workflow Versioning for long histories.
- Persist terminal state in a `finally` path.

## 7. Rollout

1. Shadow-create task and ledger records without changing existing execution.
2. Compare old and new state/progress/cost results.
3. Enable admission control for internal tenants.
4. Enable 1%, 5%, 20%, 50%, and 100% cohorts with rollback gates.
5. Reconcile every cohort before expansion.
6. Keep an emergency kill switch that stops new admission but does not destroy durable state.

## 8. Completion evidence

A repository adoption is complete only when all hard gates pass with actual database, Temporal, broker, object store, provider, and payment fixtures. Specification conformance alone is insufficient.
