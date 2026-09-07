# Scheduler

## Scheduling hierarchy

Use fair scheduling before priority:

1. tenant
2. account
3. project
4. job type
5. work item priority

Weighted fair queuing or deficit round robin are suitable.

## Admission limits

Enforce:
- running jobs
- running work items
- concurrent model calls
- per-project parallelism
- sandbox capacity
- compile/test slots
- provider rate limits
- daily token/credit caps

## Bounded READY frontier

Do not materialize millions of READY rows when only thousands can execute.

Expand the dependency frontier in bounded batches and favor critical-path unblocking work.
