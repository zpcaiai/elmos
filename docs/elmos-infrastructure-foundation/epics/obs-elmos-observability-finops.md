# Unified Observability, Profiling, Runtime ETA, and FinOps

- Skill: `elmos-observability-finops`
- Priority: `P1`
- Phase: `G8`
- Dependencies: `elmos-temporal-task-reliability`, `elmos-runner-scheduler-execution`, `elmos-model-gateway-agent-runtime`, `elmos-evidence-pack-offline-verification`

## Objective

Make every slow, failed, expensive, low-quality, or stuck project diagnosable and provide calibrated autonomous system runtime estimates distinct from human-equivalent effort.

## Task groups

### Telemetry conventions

- [ ] `ELMOS-OBS-001` Define spans/events for API, project, workflow, activity, lease, action, sandbox, transfer, cache, parser/IR/rule, model/tool, build/test, evidence, promotion, and recovery.
- [ ] `ELMOS-OBS-002` Propagate trace/correlation identifiers through HTTP, gRPC, Temporal, messages, runner protocol, model gateway, and artifact metadata.
- [ ] `ELMOS-OBS-003` Standardize tenant/project/workflow/task/action/runner/adapter/language/toolchain/rule/model/cache/sandbox/validation attributes.
- [ ] `ELMOS-OBS-004` Hash or omit sensitive tenant/source values and apply centralized redaction.
- [ ] `ELMOS-OBS-005` Separate management endpoints/network and protect telemetry export.

### Metrics and SLOs

- [ ] `ELMOS-OBS-006` Measure workflow starts/failures/stuck/duration/retries/heartbeat lag.
- [ ] `ELMOS-OBS-007` Measure queue age, lease expiry, unknown result, runner health/load, sandbox startup, transfer, and capacity.
- [ ] `ELMOS-OBS-008` Measure CAS/action/parse/IR/toolchain/prefix/response cache hits, misses, corruption, evictions, and bytes avoided.
- [ ] `ELMOS-OBS-009` Measure model requests/tokens/cost/latency/budget rejection/tool calls/iterations/repair success.
- [ ] `ELMOS-OBS-010` Measure compile/test/contract/behavior/performance/security/evidence/certification/PR quality outcomes.
- [ ] `ELMOS-OBS-011` Define availability, correctness, durability, recovery, latency, and freshness SLOs with burn-rate alerts.

### Logs, dashboards, and alerts

- [ ] `ELMOS-OBS-012` Emit structured logs with trace/correlation and schema versions.
- [ ] `ELMOS-OBS-013` Build system health, workflows, runner fleet, cache, model cost, quality/certification, tenant usage, storage, and DR dashboards.
- [ ] `ELMOS-OBS-014` Alert on queue age, lease/reaper anomalies, stuck workflow, CAS corruption, model budget spikes, evidence gaps, security denials, backup/restore failure, and SLO burn.
- [ ] `ELMOS-OBS-015` Attach owner, severity, runbook, deduplication, and escalation to each alert.
- [ ] `ELMOS-OBS-016` Test alerts through synthetic failure injection.

### Continuous profiling

- [ ] `ELMOS-OBS-017` Profile Java control plane/Temporal workers, Go runners, Python engines, native compilers, and inference services.
- [ ] `ELMOS-OBS-018` Correlate CPU, heap, allocation, lock, goroutine/thread, I/O, and flame profiles to actions/toolchains.
- [ ] `ELMOS-OBS-019` Detect repeated large-file reads, dependency downloads, serialization, low cache reuse, N+1 queries, queue contention, and high-token low-success paths.
- [ ] `ELMOS-OBS-020` Store profile summaries/evidence under retention policy without source leakage.

### Cost ledger and FinOps

- [ ] `ELMOS-OBS-021` Record compute CPU/memory/GPU time, runner startup/idle, storage, transfer, observability, provider tokens, licenses, and human review.
- [ ] `ELMOS-OBS-022` Aggregate by tenant, portfolio, project, workflow, stage, action, adapter, model, and certification.
- [ ] `ELMOS-OBS-023` Track estimate, reservation, actual, forecast, variance, refund, retry waste, cache savings, and cost per verified work unit.
- [ ] `ELMOS-OBS-024` Implement soft/hard budgets, anomaly detection, allocation tags, approval, and forecast.
- [ ] `ELMOS-OBS-025` Do not count transfers or retries twice.

### Autonomous runtime estimation

- [ ] `ELMOS-OBS-026` Predict eLMOS machine wall-clock duration from repository features, changed work units, cache state, queue/capacity, runner/toolchain locality, historical stage durations, model rate/latency, validation scope, retries, and uncertainty.
- [ ] `ELMOS-OBS-027` Return P50/P80/P95 duration ranges, confidence, assumptions, critical path, queue time, execution time, and risk drivers.
- [ ] `ELMOS-OBS-028` Continuously recalibrate estimates from actual stage completion and residual work.
- [ ] `ELMOS-OBS-029` Never express system ETA as developer person-days or include human waiting unless separately labeled.
- [ ] `ELMOS-OBS-030` Provide a separate human-equivalent estimate for manual implementation/review and clearly state it is a comparison, not the eLMOS runtime.
- [ ] `ELMOS-OBS-031` Persist estimate revisions and accuracy metrics in evidence.

### Operational data quality

- [ ] `ELMOS-OBS-032` Validate clock synchronization, duplicate events, missing spans, sampling bias, cost completeness, price version, and metric-label cardinality.
- [ ] `ELMOS-OBS-033` Reconcile model provider usage, runner records, object storage, and billing ledger.
- [ ] `ELMOS-OBS-034` Annotate dashboards/estimates when coverage is partial.

## Validation

- [ ] Trace one project end-to-end through workflow, runner, model, verification, evidence, and promotion.
- [ ] Inject secrets/source into fields and verify redaction.
- [ ] Trigger each critical alert and validate runbook links.
- [ ] Reconcile duplicate retries and provider usage without double cost.
- [ ] Backtest runtime P50/P80/P95 estimates on cold, warm, partial-change, and queued runs.

## Exit gate

- [ ] A failed or expensive project is attributable to exact stages/actions.
- [ ] Critical SLOs and alerts are tested and actionable.
- [ ] Costs and cache savings reconcile to source records.
- [ ] System runtime ETA is calibrated, uncertainty-aware, and distinct from human-equivalent effort.
