# Architecture Specification

## A. Control Plane Integration

Elmos controls project generation through a durable workflow:

1. **Request Snapshot** — immutable user inputs, repository snapshot, file hashes, scope authorization.
2. **Requirement IR** — database and big-data-specific normalized requirements.
3. **Evidence Registry Snapshot** — selected capability catalog, rules, official evidence and benchmark versions.
4. **Decision DAG** — hard constraints, ranking, portfolio, pattern and ADR.
5. **Generation DAG** — contracts, pipelines, storage, serving, governance, infrastructure, tests and documentation.
6. **Verification DAG** — static, component, integration, E2E, performance, chaos, security, recovery.
7. **Repair Loop** — bounded repair attempts with snapshot, canary, regression and rollback.
8. **Evidence & Handoff** — E1–E5 scorecard, runbooks, cost, ETA and unresolved risks.

Temporal or an equivalent durable workflow engine owns the Elmos long-running control workflow. Airflow or Dagster may be generated for data asset/workload orchestration; they are not substitutes for Elmos tenant scheduling, model routing and repository generation state.

## B. Planes

| Plane | Responsibilities |
|---|---|
| Browser/API | Requirement upload, choices, status, evidence, project download |
| Control | Tenant quota, max 3 concurrent tasks, workflow state, approvals, cancellation |
| Analysis | IR extraction, profiling, candidate filtering, ranking, benchmarks, ADR |
| Generation | Code, configuration, schemas, connectors, pipelines, IaC, tests, docs |
| Verification | Functional/data/performance/security/recovery validation and repair |
| Artifact | Immutable generated repository, evidence, reports, diagrams and handoff |
| Storage | PostgreSQL metadata, object storage artifacts, graph/lineage, search, cache |

All storage implementations must sit behind replaceable interfaces.

## C. Core IRs

### WorkloadRequirementIR

Captures 5V, sources, consumers, SLOs, query/write patterns, transactions, consistency, security, residency, deployment, budget, operations maturity and assumptions.

### DatabaseDecisionIR

Captures role-level feasible candidates, rejected candidates, constraint proofs, MCDA scores, Pareto frontier, sensitivity, selected portfolio and evidence.

### DataProjectIR

Captures project classification, architecture patterns, data roles, contracts, pipelines, models, serving, governance, deployment, verification, cost and ETA.

### EvidenceBundle

Captures claims and their status: implemented, configured, tested, verified or certified. It includes environment, version, artifact checksum, evidence URI, scope and gaps.

## D. Selection Pipeline

```text
Requirement IR
  -> profile
  -> hard constraints
  -> role decomposition
  -> candidate portfolios
  -> MCDA/Pareto/uncertainty
  -> complexity penalty
  -> benchmark/cost
  -> architecture decision
```

The engine never converts a hard failure into a low score. It first rejects candidates that violate security, residency, transaction, capacity, deployment or recovery constraints.

## E. Architecture Pattern Rules

- **Batch-first**: bounded data and historical recomputation dominate.
- **Streaming-first/Kappa**: replayable durable log and continuous stateful processing dominate.
- **Lambda**: batch and speed layers require genuinely different logic or engines.
- **Unified bounded/unbounded**: one dataflow model can express both, while runtime and sink semantics remain explicit.
- **Lakehouse**: open table format, object storage, history, time travel and multi-engine access dominate.
- **Federated query**: data cannot be centralized or transition requires cross-source access.
- **Data Fabric**: metadata, policy, discovery, lineage, quality and automation overlay.
- **Data Mesh**: domain ownership and federated governance operating model.
- **Polyglot persistence**: separate data roles with one authoritative source and rebuildable read models.

## F. Repository Generation Contract

The generator must emit:

- runnable source code;
- dependency and version locks;
- local Docker profile;
- production IaC profile;
- sample/seed data;
- data and event contracts;
- unit, contract, quality, integration, E2E, performance, chaos and security tests;
- observability and Data SLO dashboards;
- ADR, architecture/data-flow diagrams, runbooks and handoff;
- evidence and limitations.

A file existing is not evidence that an integration works. Every provider-specific claim must cite a test or be labeled planned/configured.

## G. Failure Semantics

Every workflow node declares:

- immutable input hash;
- idempotency key;
- side-effect class;
- retry policy;
- timeout;
- compensation or rollback;
- output checksum;
- resumable checkpoint;
- tenant and authorization scope.

High-risk data mutation, destructive migration, permission broadening or production cutover requires an approval policy and a fresh restore point.

## H. Cache Rules

Cache keys include:

```text
tenant_id + repository_snapshot + requirement_ir_hash + target_profile_hash
+ registry_snapshot + generator_version + model_route + toolchain_lock
```

Raw sensitive data is excluded by default. Cached artifacts are encrypted, access-controlled, TTL-bound and invalidated when any semantic input changes.

## I. Production Readiness Levels

| Level | Meaning |
|---|---|
| E0 | Draft or unvalidated design |
| E1 | Static package and schema integrity |
| E2 | Local/component runtime evidence |
| E3 | Integration and end-to-end evidence |
| E4 | Production-like performance, chaos, security and recovery |
| E5 | Controlled production or shadow evidence and operating loop |

No level may be inferred from documentation alone.
