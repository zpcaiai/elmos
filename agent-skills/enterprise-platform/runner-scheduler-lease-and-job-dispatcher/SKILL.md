---
name: runner-scheduler-lease-and-job-dispatcher
description: Match tenant jobs to authorized Runner pools by isolation, toolchain, network, residency, capacity, quota, risk, and maintenance window. Use for lease, heartbeat, recovery, or dispatch design.
---

# Runner Scheduler Lease and Job Dispatcher

Read `../references/batch-12-enterprise-platform.md`. Prefer Runner-initiated outbound claim, issue short leases and job-scoped tokens, enforce execution locks for non-idempotent stages and recover expired leases without double submission. Preserve fair scheduling and Offline constraints.

Cross-tenant claims, long-term secrets or duplicate non-idempotent work blocks T-C.
