---
name: behavioral-equivalence-orchestrator
description: "Orchestrate Batch 9 source-target dual runs, OBM collection, differential Oracles, Golden evidence, repair feedback, and E-A through E-E gates. Use for an end-to-end behavioral-equivalence validation run."
---

# Behavioral Equivalence Orchestrator

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Verify Batch 8 R-D admission and freeze both Snapshots.
2. Align isolated runtimes, scenarios, observation points, clocks, random streams, external recordings and trusted Golden versions.
3. Schedule matching clean runs, collect raw and canonical observations, invoke required Oracles and classify every difference.
4. Route evidenced regressions to Batch 8, persist immutable evidence and evaluate each module independently.

## Hard rules

- Never execute customer code or production traffic in the control plane.
- Never convert unknown, not-comparable, flaky or Agent opinion into equivalence.
- Authorize production hardening only at E-D or E-E and always leave cutover false.

## Output

Produce a reproducible run manifest, comparison stream, repair feedback and per-module conformance report.

