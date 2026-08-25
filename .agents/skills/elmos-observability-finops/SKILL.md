---
name: elmos-observability-finops
description: Correlate traces, metrics, logs, profiles, quality, cache, capacity,
  wall-clock estimates, and cost across control plane, workflows, runners, models,
  verification, and delivery.
version: 1.0.0
priority: P1
phase: G8
dependencies:
- elmos-temporal-task-reliability
- elmos-runner-scheduler-execution
- elmos-model-gateway-agent-runtime
- elmos-evidence-pack-offline-verification
---

# Unified Observability, Profiling, Runtime ETA, and FinOps

## Objective

Make every slow, failed, expensive, low-quality, or stuck project diagnosable and provide calibrated autonomous system runtime estimates distinct from human-equivalent effort.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Unified Observability, Profiling, Runtime ETA, and FinOps** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-temporal-task-reliability`
- `elmos-runner-scheduler-execution`
- `elmos-model-gateway-agent-runtime`
- `elmos-evidence-pack-offline-verification`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Telemetry must not contain raw private source or secrets.
- High-cardinality identifiers belong in traces/logs, not unbounded metric labels.
- Runtime ETA is machine wall-clock time for eLMOS execution, not person-days.
- Estimated, reserved, actual, forecast, and human-equivalent values remain separate.

## Required inputs

- Service/workflow/action/model/evidence schemas.
- Resource prices, quotas, queues, historical durations, and quality outcomes.
- SLOs, retention, sampling, and alert policies.

## Required outputs

- `OpenTelemetry conventions and propagation.`
- `Dashboards, alerts, runbooks, continuous profiles.`
- `Cost ledger and budgets.`
- `Calibrated system runtime ETA and human-equivalent comparison.`

## Repository discovery

Before editing:

1. Locate `AGENTS.md`, `CLAUDE.md`, repository-local Skills, architecture decision records, manifests, schemas, migrations, and build commands.
2. Identify actual control-plane, workflow, runner, engine, web, database, object-store, policy, telemetry, and test modules; do not assume the reference layout exists.
3. Search for existing contracts and implementations before creating duplicates.
4. Record current behavior, known gaps, security boundaries, external side effects, and the exact validation commands that are available.
5. Create or update a durable implementation plan from `templates/IMPLEMENTATION-PLAN.yaml`.

## Execution workflow

1. Select the smallest dependency-resolved vertical slice.
2. Freeze input snapshots, schema/toolchain/policy versions, and rollback boundaries.
3. Implement contract/schema changes before consumers, using backward-compatible transitions.
4. Implement production behavior, authorization, idempotency, telemetry, audit, failure handling, tests, documentation, and runbooks together.
5. Execute focused tests, integration tests, race/failure tests, security tests, and clean-environment reproduction as applicable.
6. Save large outputs by digest; record commands, results, durations, cost, evidence, and residual risk.
7. Report autonomous **system wall-clock runtime** separately from human-equivalent engineering/review effort.
8. Never claim production completion from generated files or static validation alone.

## Implementation checklist

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

## Required artifacts

At minimum, produce or update:

- Versioned contracts and schemas.
- Database migrations and compatibility/rollback notes where state changes.
- Production implementation with explicit authorization, idempotency, retries, cancellation, and failure classification as applicable.
- Unit, integration, end-to-end, race/failure, and security tests appropriate to risk.
- OpenTelemetry instrumentation, operational metrics, alerts, and runbooks for production components.
- Audit/evidence records with immutable input and output digests.
- Updated architecture and operational documentation.
- Task report based on `templates/TASK-REPORT.md`.

## Validation

- [ ] Trace one project end-to-end through workflow, runner, model, verification, evidence, and promotion.
- [ ] Inject secrets/source into fields and verify redaction.
- [ ] Trigger each critical alert and validate runbook links.
- [ ] Reconcile duplicate retries and provider usage without double cost.
- [ ] Backtest runtime P50/P80/P95 estimates on cold, warm, partial-change, and queued runs.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] A failed or expensive project is attributable to exact stages/actions.
- [ ] Critical SLOs and alerts are tested and actionable.
- [ ] Costs and cache savings reconcile to source records.
- [ ] System runtime ETA is calibrated, uncertainty-aware, and distinct from human-equivalent effort.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
