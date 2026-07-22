---
name: repair-loop-orchestrator
description: "Orchestrate Batch 8 dependency restore, build, static analysis, test, diagnosis, bounded repair, regression, rollback, and stopping. Use for an end-to-end repair run over a migrated target repository."
---
# Repair Loop Orchestrator
Read `../references/batch-8-repair-loop.md` and validate inputs against `contracts/repair-loop-schema/repair-run-manifest.schema.json`.

Verify Batch 7 admission and source/target baselines, plan the build matrix, execute through the isolated authority, normalize and cluster failures, attribute them, select one repair plan, apply one transactional patch, validate affected and full scope, and record progress. Preserve the last stable Snapshot at every transition.

Prefer deterministic repair. Invoke an Agent only for an evidenced cluster and bounded plan. Stop on risk, environment, budget, oscillation, no progress or human decision. Report partial convergence explicitly; never equate a passing build with Batch 8 convergence.
