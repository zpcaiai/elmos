---
name: transaction-write-trace-and-atomicity-comparator
description: "Compare Batch 9 transaction boundaries, write order, commit, rollback, retry, locks, outbox and atomicity. Use for normal and injected-failure transaction scenarios."
---

# Transaction Write Trace and Atomicity Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Capture logical transaction and write-event sequences.
2. Inject failures around writes, message send, external call and commit.
3. Compare rollback, partial writes, retries, isolation outcomes and message-after-commit relations.

## Hard rules

- Never infer atomicity from equal final state.
- Treat partial commit and deadlock as critical.
- Validate multi-resource and outbox behavior explicitly.

## Output

Emit transaction traces, fault location and atomicity verdicts.

