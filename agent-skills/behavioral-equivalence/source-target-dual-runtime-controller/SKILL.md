---
name: source-target-dual-runtime-controller
description: "Provision and govern isolated source and target runtimes for Batch 9. Use when creating dual-container, process, namespace, cluster, or record-source/replay-target environments."
---

# Source Target Dual Runtime Controller

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Pin runtime images and source/target Snapshots.
2. Allocate separate mutable resources, identities, ports, topics, caches, files and scheduler locks.
3. Provision, configure, seed, start, await readiness, execute, drain, capture, shut down and clean up.

## Hard rules

- Forbid shared mutable state and target access to source or production resources.
- Disable schedulers unless explicitly tested.
- Stop on readiness or cleanup uncertainty and preserve the environment manifest.

## Output

Return readiness, isolation, cleanup and evidence state without claiming behavioral success.

