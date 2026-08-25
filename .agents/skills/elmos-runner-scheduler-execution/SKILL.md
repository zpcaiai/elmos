---
name: elmos-runner-scheduler-execution
description: Define a portable action protocol, capability-aware runners, fair scheduling,
  data-local execution, sharding, warm pools, and resumable transfer.
version: 1.0.0
priority: P1
phase: G4
dependencies:
- elmos-temporal-task-reliability
- elmos-content-addressed-cache
- elmos-reproducible-toolchain
- elmos-identity-tenant-security
---

# Remote Execution, Runner Fleet, Scheduling, and Artifact Transfer

## Objective

Execute build, conversion, validation, and model-support tasks across heterogeneous private and managed environments safely and efficiently.

## Use this skill when

Use this skill when implementing, repairing, reviewing, validating, or productionizing the **Remote Execution, Runner Fleet, Scheduling, and Artifact Transfer** capability in an eLMOS repository. Invoke the program orchestrator first for work spanning multiple skills.

## Dependencies

- `elmos-temporal-task-reliability`
- `elmos-content-addressed-cache`
- `elmos-reproducible-toolchain`
- `elmos-identity-tenant-security`

Do not mark this skill complete until required dependency contracts are present and their blocking gates pass. A dependency can be implemented in the same change only when the plan preserves reviewable boundaries.

## Non-negotiable constraints

- Scheduler selects only runners satisfying toolchain, sandbox, residency, identity, and resource requirements.
- Fairness/quotas prevent monopolization.
- Successful shards are not rerun because another shard fails.
- Large artifacts move by digest/chunk manifest.

## Required inputs

- Action/toolchain contracts.
- Runner identities/capabilities.
- Queues, quotas, priorities, residency rules.
- CAS/transfer endpoints.

## Required outputs

- `Versioned Action/ActionResult.`
- `Capability registration.`
- `Fair locality-aware scheduler.`
- `Fleet lifecycle/autoscaling.`
- `Sharding and resumable transfer.`

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

### Action protocol

- [ ] `ELMOS-RUN-001` Define Action with action digest, input root, toolchain, command, environment, working directory, outputs, resources, sandbox, network, secrets, timeout, priority, tenant, and project.
- [ ] `ELMOS-RUN-002` Define ActionResult with status, receipt, output manifest, exit code, logs, duration, resources, cost, validation, and provenance.
- [ ] `ELMOS-RUN-003` Require declared outputs and do not upload arbitrary workspace contents.
- [ ] `ELMOS-RUN-004` Check Action Cache before execution and publish valid results after completion.
- [ ] `ELMOS-RUN-005` Negotiate protocol versions and reject incompatible runners.
### Capabilities and health

- [ ] `ELMOS-RUN-006` Register OS, architecture, CPU, memory, disk, GPU, sandbox tiers, region, residency, network, prewarmed toolchains, cache summary, concurrency, and load.
- [ ] `ELMOS-RUN-007` Refresh capability on image, hardware, policy, or connectivity changes.
- [ ] `ELMOS-RUN-008` Bind capabilities to authenticated runner identity.
- [ ] `ELMOS-RUN-009` Expose heartbeat, drain, maintenance, disabled, unhealthy, and quarantine states.
- [ ] `ELMOS-RUN-010` Prevent incompatible/revoked runners from leasing.
### Fair scheduling

- [ ] `ELMOS-RUN-011` Implement priority classes, weighted fairness, tenant/project/task quotas, priority aging, deadlines, and bounded preemption.
- [ ] `ELMOS-RUN-012` Prevent noisy neighbors across runners, models, storage, network, and queues.
- [ ] `ELMOS-RUN-013` Reserve resources before lease and release on terminal/expired states.
- [ ] `ELMOS-RUN-014` Expose queue age, estimated start, no-runner reason, quota, and capacity forecast.
- [ ] `ELMOS-RUN-015` Require approval for quota/budget override.
### Locality and placement

- [ ] `ELMOS-RUN-016` Prefer runners holding inputs, dependency caches, and toolchains.
- [ ] `ELMOS-RUN-017` Balance locality against queue delay, transfer, startup, security, and residency.
- [ ] `ELMOS-RUN-018` Record placement scores and explanation.
- [ ] `ELMOS-RUN-019` Support region/customer-network affinity.
- [ ] `ELMOS-RUN-020` Avoid raw-source movement when private runner can execute locally.
### Fleet modes

- [ ] `ELMOS-RUN-021` Support trusted native local, rootless container, Kubernetes Job, warm Deployment, external private, Windows, macOS/Swift, ARM, and GPU runners.
- [ ] `ELMOS-RUN-022` Implement safe drain, certificate rotation, image rollout, and maintenance.
- [ ] `ELMOS-RUN-023` Autoscale warm pools from queue age, demand, cold-start cost, and forecast.
- [ ] `ELMOS-RUN-024` Keep capability labels immutable for the leased task.
### Sharding and recovery

- [ ] `ELMOS-RUN-025` Partition large repositories by module, dependency graph, work unit, or tests.
- [ ] `ELMOS-RUN-026` Store shard inputs/outputs in CAS with explicit dependencies.
- [ ] `ELMOS-RUN-027` Retry only failed shards.
- [ ] `ELMOS-RUN-028` Quarantine repeatedly failing shards while independent work continues.
- [ ] `ELMOS-RUN-029` Aggregate shard results deterministically into project/portfolio evidence.
### Artifact transfer

- [ ] `ELMOS-RUN-030` Transfer large artifacts with chunk manifests, hashes, encryption, compression, deduplication, resume, region policy, and bandwidth budget.
- [ ] `ELMOS-RUN-031` Verify every chunk and final manifest.
- [ ] `ELMOS-RUN-032` Clean incomplete sessions after reconciliation/retention.
- [ ] `ELMOS-RUN-033` Measure bytes transferred, avoided, retried, and rejected.

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

- [ ] Register incompatible, revoked, overloaded, and stale runners and reject work.
- [ ] Stress weighted fairness with multiple tenants/priorities.
- [ ] Test locality versus queue delay explanations.
- [ ] Fail one shard and preserve successful shards.
- [ ] Interrupt large transfers and verify exact final digest.

Run repository-native format, lint, typecheck, unit, integration, packaging, and security commands. Also run the package validators when Skill content or schemas change:

```bash
python3 scripts/validate_skill_bundle.py
python3 scripts/validate_json_schemas.py
python3 -m unittest discover -s tests -v
```

## Definition of done

- [ ] Every action runs on a compatible authorized runner.
- [ ] No tenant starves the fleet beyond policy.
- [ ] Placement is explainable and residency-compliant.
- [ ] Shard/transfer failure recovers without restarting successful work.

Additionally:

- [ ] No placeholder, TODO-only, mock-only, or documentation-only implementation is counted as production completion.
- [ ] All modified public contracts are versioned and compatibility-tested.
- [ ] All side effects are idempotent or reconciled.
- [ ] Critical actions are authorized, audited, and observable.
- [ ] Evidence identifies exact source, toolchain, rule/model/policy, commands, results, and residual risk.
- [ ] Static bundle validation is described accurately as structural validation only.

## Failure handling and handoff

Classify failures as `ENVIRONMENT`, `DEPENDENCY`, `CODE`, `POLICY`, `SECURITY`, `DATA`, `CAPACITY`, `PROVIDER`, or `UNKNOWN`. Preserve successful checkpoints. Put ambiguous side effects in `UNKNOWN_RESULT`/`MANUAL_RECOVERY`; reconcile before retrying. Update the implementation plan with status, commit, commands, measured wall-clock duration, cost, evidence digest, blockers, and the next dependency-resolved task.
