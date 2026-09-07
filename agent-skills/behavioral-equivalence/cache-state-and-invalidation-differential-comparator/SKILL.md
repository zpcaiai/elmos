---
name: cache-state-and-invalidation-differential-comparator
description: "Compare Batch 9 cache keys, namespaces, values, TTL, hit/miss, eviction and transaction order. Use for local or distributed cache behavior."
---

# Cache State and Invalidation Differential Comparator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Capture put/get/miss/evict/null and transaction relations.
2. Drive TTL, sliding expiry and refresh with the shared virtual clock.
3. Compare serialization, namespaces, stampede, fail-open and downstream call counts.

## Hard rules

- Treat tenant-key drift as critical.
- Do not compare only final cache state.
- Detect cache writes after rollback and TTL rounding differences.

## Output

Emit cache event/state diffs with timing and isolation evidence.

