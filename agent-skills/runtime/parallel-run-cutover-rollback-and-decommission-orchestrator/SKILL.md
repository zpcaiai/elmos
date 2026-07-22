---
name: parallel-run-cutover-rollback-and-decommission-orchestrator
description: Orchestrate mainframe online shadow, dual execution, read comparison, batch/file parallel runs, message mirrors, progressive cutover, rollback, stability hold, read-only transition, and evidence-based decommission. Use for CICS/IMS traffic shifts, batch scheduler switches, writer changes, or legacy retirement.
---

# Mainframe Parallel Run and Cutover

## Run in parallel

1. Separate online shadow from batch parallel execution.
2. Suppress, redirect, roll back, or isolate shadow side effects; forbid uncontrolled dual writers.
3. Freeze batch input generation, Db2/VSAM snapshot, parameters, calendar, and runtime versions for both paths.
4. Compare transaction outputs, files, messages, reports, data states, control totals, errors, and performance.
5. Shift by transaction, route, customer, region, job, scheduler, dataset, message, report, or writer with explicit approval and evidence.

## Roll back and retire

- Model route, transaction, schedule, writer, data-repair, full-capability rollback, and forward-fix options before cutover.
- Record points of no return such as new-only state, removed layouts/modules, deleted datasets, rewired schedules, and cancelled licenses.
- Decommission only after transaction, job, dataset, module, and external-consumer usage are zero; archive evidence; revoke RACF/credentials; update scheduler, DR, and runbooks.
