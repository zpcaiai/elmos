---
name: observable-effect-collector
description: "Collect Batch 9 HTTP, database, transaction, message, file, cache, external-call, error, audit, metric and resource effects. Use when implementing or operating OBM collectors."
---

# Observable Effect Collector

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Capture before, during, after success, failure, rollback and shutdown.
2. Preserve raw references, logical sequence, collector version, sensitivity and evidence.
3. Report completeness independently for each observation type.

## Hard rules

- Prefer read-only collection and never alter transactions, acknowledgements, files or resource lifetime.
- Avoid business getters and lazy-loading side effects.
- Report collector failure as collector failure, not regression.

## Output

Emit protocol-conformant source or target observations with explicit completeness.

