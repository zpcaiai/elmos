---
name: differential-execution-scheduler
description: "Schedule Batch 9 paired source-target scenarios by dependency, risk, resource, order and clean-run policy. Use for sequential, parallel-isolated, record/replay, paired-batch or coordinated concurrency execution."
---

# Differential Execution Scheduler

Read `../references/batch-9-behavioral-equivalence.md` before acting. Validate machine artifacts against `contracts/behavior-equivalence-schema` and use `modules/behavior-equivalence` as the authoritative control-plane boundary.

## Workflow

1. Respect seed, broker, recording, resource and scenario dependencies.
2. Run selected cases source-first and target-first to detect pollution.
3. Enforce per-scenario timeout, repeat critical cases and perform final clean runs.

## Hard rules

- Never parallelize scenarios sharing mutable state.
- Keep scheduler failure separate from behavior regression.
- Do not use one incremental pass as the final gate.

## Output

Emit a deterministic schedule, resource rationale and per-run evidence.

