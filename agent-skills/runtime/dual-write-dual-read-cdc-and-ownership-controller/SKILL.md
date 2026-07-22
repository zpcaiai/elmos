---
name: dual-write-dual-read-cdc-and-ownership-controller
description: Govern single-writer, dual-write, dual-read, outbox/inbox, CDC, and explicit data ownership transitions. Use when Batch 13 moves state between legacy and modern systems.
---

# Dual Write, Dual Read, CDC, and Ownership Controller

## Rules

Maintain one explicit authoritative writer and store whenever possible. Treat sequential dual-write success as false if either side fails. Separate read cutover from write ownership.

## Workflow

1. Record data asset, authoritative writer/store, replicas, state, effective time, and evidence.
2. Prefer transactional outbox/inbox, idempotent consumers, CDC, or compensating workflows over unprotected sequential dual writes.
3. Track source/applied positions, time/record/transaction lag, retry/error queues, connector health, and resumability.
4. For reads, define legacy-only, shadow-compare, legacy-primary fallback, new-primary fallback, or new-only explicitly.
5. Never promote `NEW_AUTHORITATIVE` without reconciliation, consumer readiness, rollback evidence, idempotency proof, and business-owner approval.
6. Suppress duplicate messages by stable message ID and preserve the decision as evidence.

## Failure states

Return `PARTIAL_WRITE`, `CDC_LAG_EXCEEDED`, `WRITE_OWNERSHIP_CONFLICT`, or `DATA_RECONCILIATION_FAILED` instead of optimistic success.
