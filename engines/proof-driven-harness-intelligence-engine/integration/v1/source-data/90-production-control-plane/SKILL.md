---
name: elmos-production-control-plane
description: Durable multi-tenant execution, recovery, ownership, fencing, metering, ETA, audit, observability, and operator control.
priority: P0
---

# K9 — Commercial Production Control Plane

## Skills

### Durable execution
- durable-job
- durable-phase
- durable-agent-state
- durable-tool-effect
- idempotency-key
- checkpoint-resume
- crash-recovery
- replay-safe-recovery
- provider-session-rotation
- provider-stream-fresh-reset
- session-fork
- job-fork

### Ownership / concurrency
- tenant-isolation
- project-isolation
- workspace-ownership
- lease-management
- lease-expiry
- fencing-token
- stale-worker-rejection
- distributed-lock-policy
- side-effect-outbox

### Operator controls
- pause-job
- resume-job
- cancel-job
- retry-phase
- replay-scenario
- steer-agent
- kill-agent
- revive-agent
- rollback-transaction
- fork-job

### Metering
- token-meter
- model-cost-meter
- tool-cost-meter
- compute-meter
- storage-meter
- project-cost-rollup
- tenant-cost-rollup
- revenue-meter
- margin-estimator

### Progress / ETA
- progress-model
- phase-completion-estimator
- wall-clock-eta
- critical-path-estimator
- retry-risk-adjustment
- repository-size-adjustment

### Observability
- trace-correlation
- structured-events
- audit-log
- evidence-provenance
- artifact-lineage
- metrics-endpoint
- health-endpoint
- version-endpoint
- readiness
- liveness
- sla-monitor
- capacity-planner
- quota-governor

## State model

QUEUED
→ PREFLIGHT
→ PLANNING
→ EXECUTING
→ VERIFYING
→ CERTIFYING
→ READY_TO_RELEASE
→ RELEASED

Side states:
PAUSED / BLOCKED / RETRYING / ROLLING_BACK / FAILED / CANCELLED / QUARANTINED

## Hard requirements

- externally visible effects MUST have durable idempotency semantics;
- stale worker MUST be rejected through fencing;
- resume MUST not double-charge or duplicate writes;
- ETA MUST report machine wall-clock estimate, not human-days;
- metering data MUST reconcile with provider/tool execution records.

## Acceptance

Demonstrate restart during each major phase with no loss of committed progress and no duplicate side effects.
