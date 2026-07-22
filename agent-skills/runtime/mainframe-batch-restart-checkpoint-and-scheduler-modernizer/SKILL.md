---
name: mainframe-batch-restart-checkpoint-and-scheduler-modernizer
description: Modernize JCL batch jobs, steps, sorts, files, GDGs, checkpoints, restart, cleanup, calendars, enterprise schedules, and batch cutover. Use for distributed batch, Kubernetes jobs, data pipelines, managed schedulers, or retained z/OS batch improvement.
---

# Mainframe Batch Modernization

## Preserve execution semantics

1. Classify steps as extract, sort, merge, transform, calculate, database update, file generation, report, transfer, archive, or control.
2. Record idempotency, checkpoint, input/output generation, commit frequency, partial results, cleanup, restart command, and irreversibility per step.
3. Capture sort keys, direction, collation, numeric format, include/omit, SUM, joins, and output layout.
4. Model GDG creation, relative references, retention, consumers, and rollback.
5. Preserve calendar, holiday, predecessor, resource, file/time trigger, late condition, rerun, operator approval, and SLA behavior.

## Validate and cut over

- Run old and new jobs from identical input and data snapshots.
- Compare each step, control total, final output, return-code policy, elapsed window, and restart behavior.
- Migrate reversible read/report jobs before settlement, ledger, month-end, external-send, and irreversible writers.
