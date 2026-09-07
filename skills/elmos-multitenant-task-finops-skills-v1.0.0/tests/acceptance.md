# Acceptance Test Matrix

Every required scenario must run against PostgreSQL with `FORCE ROW LEVEL SECURITY`, a non-superuser application role, an external Temporal test server, and at least two Control API replicas where concurrency is relevant.

| ID | Scenario | Required evidence |
|---|---|---|
| AC-MTF-001 | One account submits 100 valid tasks simultaneously. | No more than three root tasks hold slots; all remaining tasks are durable `WAITING_FOR_SLOT` records. |
| AC-MTF-002 | The same account submits through two browsers, two devices, and two tenants. | The account still owns at most three slots globally. |
| AC-MTF-003 | Two different accounts submit concurrently. | Each account can independently own up to three slots. |
| AC-MTF-004 | Duplicate task submission with the same idempotency key. | One task ID and at most one slot claim; response replay returns original result. |
| AC-MTF-005 | API crashes after task insert but before response. | Retry returns the existing task; no duplicate workflow or slot. |
| AC-MTF-006 | Admission succeeds but workflow start is interrupted. | Outbox/Update-with-Start eventually starts exactly one logical workflow. |
| AC-MTF-007 | Fourth task waits while one active task succeeds. | Released slot promotes the next eligible queued task exactly once. |
| AC-MTF-008 | A running task pauses after a durable checkpoint. | Slot is released only after checkpoint and side-effect receipts are committed. |
| AC-MTF-009 | A paused task resumes. | It re-enters admission, obtains a new slot generation, and continues from the compatible checkpoint. |
| AC-MTF-010 | Worker disappears with an expired lease. | Task enters `UNKNOWN_RESULT`, then `RECONCILING`; it is not blindly retried. |
| AC-MTF-011 | External side effect completed before worker crash. | Receipt reconciliation prevents duplicate side effect. |
| AC-MTF-012 | Checkpoint object is missing or digest-invalid. | Automatic resume is blocked and task enters manual recovery or fails by policy. |
| AC-MTF-013 | Cancellation occurs during a long-running node. | Cancellation reaches workflow, activity, runner, and sandbox; terminal state is durable. |
| AC-MTF-014 | Progress events arrive duplicated and out of order. | Projection uses transition ID and run sequence watermark; percentage never regresses improperly. |
| AC-MTF-015 | Progress projector is offline for 30 minutes. | Task execution continues; projection catches up from event log/outbox without data loss. |
| AC-MTF-016 | High-frequency logs exceed database threshold. | Segmented logs land in object storage; DB contains references, digests, and bounded summaries. |
| AC-MTF-017 | Tenant A attempts to read Tenant B tasks, inputs, outputs, events, cost, or revenue. | Every query is denied or returns no rows under real RLS. |
| AC-MTF-018 | Request presents a forged tenant header. | Tenant derives from verified identity and membership, not the header. |
| AC-MTF-019 | One task calls model, CPU, storage, egress, and third-party services. | Each immutable usage event is linked to task/run/node/attempt and uses a snapshotted price/FX basis. |
| AC-MTF-020 | Provider sends duplicate usage receipt. | Unique provider receipt/idempotency key prevents double cost. |
| AC-MTF-021 | Provider revises final usage. | Original entry remains; a correction entry creates the final reconciled value. |
| AC-MTF-022 | Fixed-project revenue is allocated across tasks. | Allocation totals exactly equal the source revenue entry within currency precision. |
| AC-MTF-023 | Refund and payment fee post after recognition. | Billed, recognized, collected, fee, tax, and refund totals remain separate and auditable. |
| AC-MTF-024 | Rebuild every operational and financial projection from source ledgers. | Rebuilt totals equal online totals; checksums and watermarks match. |
| AC-MTF-025 | Export all task history for one tenant/account. | Export contains scoped inputs/outputs metadata, events, checkpoints, costs, revenue, and audit references with secrets redacted. |
| AC-MTF-026 | Delete according to retention policy while legal hold exists. | Held artifacts remain; eligible data is deleted with an audit record. |
| AC-MTF-027 | Database failover occurs during slot claim and event insert. | Transaction is atomic; no oversubscription or missing required event. |
| AC-MTF-028 | Queue contains mixed priorities and large/small workloads. | Aging and weighted fairness prevent starvation while respecting resource units. |
| AC-MTF-029 | Tenant budget is exhausted while account has a free slot. | Task remains queued/blocked according to policy and does not start. |
| AC-MTF-030 | Full certification campaign. | Concurrency, RLS, load, chaos, recovery, financial reconciliation, and observability gates all pass or carry an expiring waiver. |

## Exit criteria

- Required acceptance tests pass on the target repository revision.
- Evidence includes commands, environment digest, database migration version, task/run IDs, traces, event sequences, wall-clock runtime, and artifact hashes.
- No production-readiness claim is based solely on mocks or in-memory stores.
