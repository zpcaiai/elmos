# SLO, Capacity, and Operational Metrics

## 1. Reliability indicators

| SLI | Initial target |
|---|---:|
| Account concurrency invariant violations | 0 |
| Cross-tenant access violations in certified tests | 0 |
| Critical task/ledger event loss after acknowledgement | 0 |
| Task create/admission API availability | 99.9% monthly target |
| Task create/admission latency | P95 ≤ 500 ms excluding uploads/external IdP |
| Slot claim latency | P95 ≤ 50 ms representative contention |
| Progress propagation lag | P95 ≤ 2 s, P99 ≤ 5 s |
| Outbox publication lag | P95 ≤ 2 s normal load |
| Supported workflow start lag after admission | P95 ≤ 5 s normal load |
| Slot release after terminal durable state | P95 ≤ 5 s |
| Snapshot rebuild correctness | exact state/count parity |
| Duplicate certified external side effects | 0 |
| Usage event duplicate billing | 0 |
| Financial projection/ledger mismatch | 0 beyond rounding policy |
| Backup restore success | 100% scheduled drills |

Targets are release gates only after target-environment measurement.

## 2. Recovery objectives

- Database RPO: according to configured PostgreSQL PITR; financial ledger target zero acknowledged-entry loss.
- Object storage RPO: versioning/replication policy.
- Task RPO: latest committed safe checkpoint.
- Task recovery detection: runner lease timeout + reaper interval.
- Supported recovery decision target: P95 ≤ 2 minutes after detection, excluding external provider ambiguity.
- Control-plane RTO: deployment-specific and proven by restore/failover drill.
- Analytics RTO may be longer because projections are rebuildable.

## 3. Capacity dimensions

Capacity planning must model:

- active root tasks;
- queued root tasks;
- node fan-out;
- task/run/event write rate;
- progress heartbeat rate;
- outbox rate/backlog;
- model request/token throughput;
- CPU/memory/GPU seconds;
- runner/site concurrency;
- object upload/download bandwidth;
- database connections/IOPS/WAL/storage;
- Temporal workflow/activity rate and history size;
- analytics scan/rollup load;
- provider/payment rate limits.

## 4. Core metrics

### Admission

```text
account_active_slots
account_waiting_tasks
slot_claim_latency
slot_lease_age
slot_reconcile_mismatch
tenant_active_tasks
tenant_concurrency_units
admission_block_total{reason}
queue_age_seconds
queue_position
scheduler_decision_latency
```

### Workflow and recovery

```text
workflow_start_lag
workflow_stuck
workflow_continue_as_new
node_duration
node_retry_total
node_heartbeat_age
runner_lease_expired
task_unknown_result
task_reconciliation_duration
task_manual_recovery
checkpoint_age
checkpoint_commit_latency
side_effect_replay_blocked
```

### Progress/event

```text
task_event_write_latency
task_event_rate
event_sequence_gap
progress_snapshot_lag
sse_connected_clients
sse_replay_count
outbox_backlog
outbox_oldest_age
outbox_dead_letter
log_buffer_bytes
telemetry_drop_total{noncritical_only}
```

### Storage

```text
artifact_upload_latency
artifact_integrity_failure
object_store_error
task_input_bytes
task_output_bytes
task_log_bytes
retention_delete_backlog
```

### FinOps/billing

```text
model_input_tokens
model_cached_input_tokens
model_output_tokens
task_estimated_cost
task_posted_cost
task_final_cost
cost_estimate_variance
budget_remaining
budget_block_total
unpriced_usage_total
usage_reconciliation_variance
recognized_revenue
collected_cash
refund_amount
unallocated_revenue
gross_profit
gross_margin
negative_margin_task_total
financial_projection_lag
```

## 5. Alerts

P0:

- concurrency invariant > 3;
- cross-tenant authorization/RLS failure;
- ledger corruption or duplicate cost/revenue;
- stale worker accepted by current lease generation;
- artifact hash mismatch on delivered/recovered result;
- persistent database/Temporal/object-store outage;
- break-glass access.

P1:

- outbox oldest age above threshold;
- stuck workflow/heartbeat;
- high unknown-result/manual-recovery rate;
- budget enforcement failure;
- unpriced usage;
- revenue allocation mismatch;
- backup/restore failure;
- negative margin spike.

P2:

- progress lag;
- queue age;
- ETA calibration error;
- cost estimate variance;
- cache hit degradation;
- provider/model cost anomaly.

## 6. Capacity benchmark phases

1. Single-node correctness baseline.
2. Multi-replica admission race.
3. Steady state across representative tenants/task mix.
4. Burst submissions and queue buildup.
5. Heavy/light noisy-neighbor test.
6. Retry storm and provider throttling.
7. Event bus outage and outbox catch-up.
8. Runner loss/recovery.
9. Database failover/PITR drill.
10. Long-duration soak with financial reconciliation.

Report autonomous wall-clock time and queue/execution/recovery components separately.

## 7. Scaling triggers

Consider event-table partitioning, separate projector services, CDC, or an analytical store only after measured triggers such as:

- retention maintenance exceeds window;
- event/usage scans affect admission latency;
- rollup jobs saturate primary database;
- outbox volume requires independent scaling;
- historical analytics requires columnar scans.

Preserve the same contracts and ledger truth when scaling.
