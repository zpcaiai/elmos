# Chaos and Recovery Test Plan

## Fault matrix

| Fault | Injection point | Expected control response |
|---|---|---|
| Control API process kill | after task insert / before response | idempotent replay; one task and one logical workflow |
| Database connection loss | during slot claim | entire transaction rolls back or commits; never partial |
| Temporal worker kill | between workflow commands | deterministic replay resumes orchestration |
| Activity worker kill | before/after side effect | lease expiry, receipt reconciliation, no blind duplicate |
| Runner network partition | while node is running | lease expires, `UNKNOWN_RESULT`, reconciliation before retry |
| Object-store timeout | checkpoint upload | checkpoint is not published until object and digest are durable |
| Corrupt checkpoint object | recovery read | digest failure blocks auto-resume |
| Event bus outage | progress publish | outbox accumulates; task execution and critical DB state continue |
| Projector crash | after consuming / before commit | idempotent replay from offset and transition ID |
| Provider timeout | model/API request | retry follows provider-safe idempotency rules and budget |
| Provider duplicate callback | usage/billing webhook | immutable ledger deduplicates by receipt/idempotency key |
| Clock skew | runner and control plane | lease comparisons use database/server time, not runner wall clock |
| Database failover | active workload | no slot oversubscription; RPO/RTO measured |
| Deployment rollback | workflow version change | compatible workers remain; replay test passes |

## Recovery evidence

For every experiment capture fault injection time, expected and observed state transitions, task/run/node attempt IDs, lease generations, last valid checkpoint, side-effect receipts, replay history, traces, recovery wall-clock time, user-visible status, and final financial reconciliation.

## Recovery objectives

- No duplicate irreversible side effects.
- No task silently disappears.
- Required event, checkpoint, usage, and revenue records have RPO 0 within the authoritative database transaction boundary.
- Workflow/control recovery RTO P95 ≤ 5 minutes for automatically recoverable faults.
- Ambiguous external outcomes enter `MANUAL_RECOVERY`; they are never reported as success without evidence.
