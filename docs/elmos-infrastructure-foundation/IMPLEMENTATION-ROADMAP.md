# Implementation Roadmap

## Release philosophy

Build one secure, durable, reproducible and evidenced vertical slice before expanding languages. A phase exits only through executed tests and evidence; generated files are not completion.

## G0

Architecture baseline, contracts, package governance, and executable plan.

- `elmos-infrastructure-program-orchestrator` — eLMOS Infrastructure Program Orchestrator
- `elmos-architecture-contract-governance` — Architecture and Contract Governance

### Exit rule

- Architecture, contracts, task plan, responsibility boundaries, and validation commands are frozen.

## G1

Identity, tenancy, authorization, database roles/RLS, runner identity, secrets, and API defense.

- `elmos-identity-tenant-security` — Identity, Tenant Isolation, Authorization, and Secrets

### Exit rule

- Tenant spoofing, IDOR, RLS bypass, shared runner credential, default secret, and secret-leak tests pass.

## G2

Temporal correctness, idempotent workflow/task protocol, leases, cancellation, checkpoints, and reconciliation.

- `elmos-temporal-task-reliability` — Temporal Workflow, Task Lease, Cancellation, and Recovery

### Exit rule

- Duplicate start/complete, runner loss, stale attempt, cancellation, checkpoint, reconciliation, and replay tests pass.

## G3

Immutable repository snapshots, CAS/action cache, staging snapshots, and reproducible toolchains.

- `elmos-repository-snapshot-workspace` — Immutable Repository Snapshot and Workspace Lease
- `elmos-content-addressed-cache` — Content-Addressed Storage and Action Cache
- `elmos-staging-snapshot-promotion` — Project Generation Staging, Sealing, Validation, and Promotion
- `elmos-reproducible-toolchain` — Reproducible Toolchains, Dependency Environments, and Warm Pools

### Exit rule

- Same immutable input/toolchain is reproducible; CAS integrity, action-key invalidation, staging seal, and safe GC pass.

## G4

Incremental semantic computation, remote execution, fleet scheduling, transfer, and tiered sandboxing.

- `elmos-incremental-semantic-index` — Incremental Parsing, Semantic Index, Impact Analysis, and Test Selection
- `elmos-runner-scheduler-execution` — Remote Execution, Runner Fleet, Scheduling, and Artifact Transfer
- `elmos-secure-sandbox-runtime` — Secure Sandbox Runtime and Capability Isolation

### Exit rule

- Incremental correctness, fair scheduling, data locality, shard recovery, transfer resume, and sandbox escape tests pass.

## G5

Canonical Semantic IR, native compiler frontends, framework/domain adapters, and deterministic rule runtime.

- `elmos-semantic-ir-compiler-platform` — Canonical Semantic IR, Compiler Frontends, and Transformation Platform

### Exit rule

- Java semantic IR is stable; native resolution, explicit gaps, source maps, and deterministic idempotent rules pass.

## G6

Model gateway, context/budget/tool governance, and the first production Java modernization loop.

- `elmos-model-gateway-agent-runtime` — Model Gateway, Context Builder, Budgeted Agent Runtime, and Inference Cache
- `elmos-java-migration-production-loop` — Production Java Modernization Closed Loop

### Exit rule

- Budgeted/tool-controlled model repair and the narrow Java end-to-end loop complete on fixtures.

## G7

Verification fabric, E1-E5 certification, Evidence Pack, policy, SBOM, provenance, and signing.

- `elmos-verification-fabric` — Verification Fabric: Build, Test, Differential Behavior, Performance, and E1-E5 Certification
- `elmos-evidence-pack-offline-verification` — Immutable Evidence Pack, Offline Verification, and Delivery Provenance
- `elmos-policy-supply-chain-signing` — Policy as Code, SBOM, SLSA Provenance, and Artifact Signing

### Exit rule

- Verification, E1-E5 status, supply-chain policy, signatures, and offline evidence verification pass.

## G8

Observability, profiling, FinOps, runtime ETA, progressive delivery, backup, restore, and disaster replay.

- `elmos-observability-finops` — Unified Observability, Profiling, Runtime ETA, and FinOps
- `elmos-progressive-delivery` — Feature Flags, Shadow Validation, Canary Rollout, and Safe Compatibility
- `elmos-backup-recovery-replay` — Backup, Restore, Disaster Recovery, Reconciliation, and Deterministic Replay

### Exit rule

- SLO/alert/runbook, cost reconciliation, calibrated system ETA, canary, restore, and disaster replay evidence pass.

## G9

Scale/fault/security benchmarks, three-repository pilot, and signed commercial production readiness gate.

- `elmos-scale-benchmark-certification` — Scale Benchmarks, Fault Injection, Security Tests, and Pilot Certification
- `elmos-production-readiness-gate` — Production Readiness and Commercial Release Gate

### Exit rule

- Scale/fault/security suites and three repeatable Java pilots support a signed scoped readiness decision.

## Parallelism rules

- Security and contracts may proceed in parallel after G0, but private-source execution waits for G1.
- CAS/Snapshot work may overlap Workflow reliability after stable IDs and tenancy contracts are frozen.
- Language/IR/model expansion does not outrun the Java deterministic and verification path.
- Observability is implemented with each component, not postponed; G8 completes cross-system operations.
- Production readiness is always last and scoped to executed evidence.
