---
name: incremental-build-and-test-scheduler
description: "Schedule affected syntax, compile, unit, contract, dependent, integration, and final full validation with safe caching and parallelism. Use after Batch 8 impact analysis."
---
# Incremental Build and Test Scheduler
Read `../references/batch-8-repair-loop.md`. Key cache entries by Snapshot, tool, configuration, lock, environment and selection hashes. Parallelize only independent modules/tests without shared mutable resources; serialize shared database, port, scheduler and compatibility-runtime cases.

Never cache flaky evidence as stable, omit full logs, reuse an unverified cache key or substitute incremental success for the final clean full regression.
