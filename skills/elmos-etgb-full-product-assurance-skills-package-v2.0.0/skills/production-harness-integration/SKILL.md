---
name: production-harness-integration
description: Integrate ETGB domain validators with the durable Elmos execution harness, adapter SDK, state machine, outbox, idempotency, and control-plane contracts.
---

# Production Harness Integration

## Invoke when

Use this Skill when ETGB moves beyond local smoke fixtures into real Spring migrations, repository translations, project generation, SQL dual-database execution, or when an existing Elmos executor must become benchmark-aware.

## Required inputs

- immutable candidate digest and immutable run-plan digest;
- tenant, account, project, task, run, shard and case-run identities;
- exact Environment/Attachment authority and fencing token;
- case document, corpus snapshot and target specification;
- budget reservation and retention policy;
- adapter implementation for the selected business line.

Reject a request that carries a mutable model alias, unfrozen plan, ambient Thread-wide permissions, missing idempotency key, or stale fencing token.

## Adapter contract

Implement every operation in `integrations/harness/adapter-contract.yaml`:

```text
prepare → baseline → transform_or_generate → build
→ validate → score → publish
```

Also implement `compensate` and `cleanup`. Each mutating operation must be idempotent. A repeated idempotency key returns the original result; it never repeats a charge, upload, migration, message, payment mock, or external write.

## Durable phase rules

1. Persist the state transition and transition audit row atomically.
2. Enter a phase only with compare-and-set on expected revision and fencing token.
3. Heartbeat the executor lease during long calls.
4. Persist a checkpoint after every successful phase and before budget-driven pause.
5. Record token, credit and wall-clock usage through an idempotent usage ledger.
6. Save raw evidence before normalization or model-generated explanation.
7. Publish lifecycle events through a transactional outbox.
8. Seal evidence before release-gate evaluation.

## Ownership and hidden-test separation

Transformation/generation workers may see source, public tests and writable target workspaces. Validation workers receive a read-only target plus hidden-test execution authority. No worker may inherit permissions from an unrelated Thread, Session or resumed executor.

## Failure handling

- Retry only classified infrastructure failures with bounded policy.
- Do not retry semantic, security, transaction or unsupported-feature failures until a new candidate digest exists.
- On pause, finish the current atomic operation, checkpoint and release the lease.
- On cancellation, stop new work, compensate durable side effects, close billing and preserve evidence.
- On ownership loss, terminate tool access immediately; a stale worker cannot publish or charge.
- If compensation fails, enter `BLOCKED` or `FAILED` with unresolved side-effect receipts.

## Reference implementation

- Python protocol/runtime: `etgb/harness.py`;
- durable local state: `etgb/state.py`;
- PostgreSQL production model: `integrations/postgres/`;
- API: `integrations/openapi/etgb-control-plane.openapi.yaml`;
- events: `integrations/events/etgb-events.asyncapi.yaml`;
- Temporal mapping: `integrations/temporal/WORKFLOW_PSEUDOCODE.md`.

## Acceptance gate

The adapter is production-eligible only after it passes every cross-cutting case for crash/resume, duplicate delivery, stale fencing, partial upload, budget exhaustion, cancellation, evidence tampering, tenant isolation and outbox recovery. An adapter that merely exposes a shell command without these guarantees remains `reference`, not production.
