---
name: concurrency-async-and-order-equivalence-validator
description: "Validate Batch 9 concurrency, async callbacks, ordering, locks, cancellation and eventual consistency. Use for races, duplicate work, deadlocks and convergence scenarios."
---

# Concurrency Async and Order Equivalence Validator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Coordinate clients with explicit barriers, seeds, repetitions and timeouts.
2. Compare strict, causal, partial-order, set or eventual relations from reviewed contracts.
3. Measure invariant outcomes and bounded convergence under fault and cancellation.

## Hard rules

- Single-thread success does not prove concurrency equivalence.
- Treat deadlock and target-only race as critical.
- Never use infinite polling or ignore causal order.

## Output

Emit reproducible schedules, happens-before evidence and invariant results.

