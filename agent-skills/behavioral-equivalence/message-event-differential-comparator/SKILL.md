---
name: message-event-differential-comparator
description: "Compare Batch 9 produced and consumed messages, commands, events, acknowledgements, retries and DLQs. Use for broker and asynchronous handler behavior."
---

# Message Event Differential Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Compare destination, type, key, payload, headers, schema, count, correlation and causation.
2. Apply only the declared global, partition, aggregate, causal or unordered relation.
3. Validate consumer state, ack timing, retry, offset, idempotency and external calls.

## Hard rules

- Unordered does not permit loss or duplication.
- Do not deduplicate all output to force a pass.
- Treat early ack, tenant drift and non-idempotent retry as regressions.

## Output

Emit message/effect diffs with ordering and transaction relations.

