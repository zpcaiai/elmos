# Remote Execution, Runner Fleet, Scheduling, and Artifact Transfer

- Skill: `elmos-runner-scheduler-execution`
- Priority: `P1`
- Phase: `G4`
- Dependencies: `elmos-temporal-task-reliability`, `elmos-content-addressed-cache`, `elmos-reproducible-toolchain`, `elmos-identity-tenant-security`

## Objective

Execute build, conversion, validation, and model-support tasks across heterogeneous private and managed environments safely and efficiently.

## Task groups

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

## Validation

- [ ] Register incompatible, revoked, overloaded, and stale runners and reject work.
- [ ] Stress weighted fairness with multiple tenants/priorities.
- [ ] Test locality versus queue delay explanations.
- [ ] Fail one shard and preserve successful shards.
- [ ] Interrupt large transfers and verify exact final digest.

## Exit gate

- [ ] Every action runs on a compatible authorized runner.
- [ ] No tenant starves the fleet beyond policy.
- [ ] Placement is explainable and residency-compliant.
- [ ] Shard/transfer failure recovers without restarting successful work.
