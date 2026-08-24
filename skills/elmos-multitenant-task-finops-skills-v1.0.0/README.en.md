# Elmos Multi-Tenant Task Control & FinOps Skills

Version: **1.0.0**  
Package: `elmos-multitenant-task-finops-skills`

This package turns the following Elmos product requirements into an implementation-ready, testable Skills program:

- Elmos runs as a multi-tenant SaaS/control plane.
- Every authenticated account may have at most **three active root tasks across all tenant memberships**.
- A fourth and later submission is stored durably as `WAITING_FOR_SLOT`; it is not discarded and does not execute until a slot is available.
- Task progress, nodes, attempts, checkpoints, leases, side effects, inputs, outputs, logs, usage, cost, revenue, and analytics are persisted.
- Long tasks support pause, resume, retry, cancellation, crash recovery, reconciliation, and idempotent completion.
- Every task has estimated, reserved, posted, and final cost.
- Historical totals include cost, billed revenue, recognized revenue, collected cash, gross profit, and gross margin.

## Architectural decisions

```text
Verified OIDC account + tenant membership
              |
              v
Spring Boot Control API
  - idempotent submission
  - global account slot claim (max 3)
  - tenant/resource/budget admission
              |
              v
PostgreSQL authoritative state + transactional outbox
              |
              +----> Temporal durable workflow
              |          |
              |          +----> workload-specific worker pools
              |          +----> private runner leases/sandboxes
              |
              +----> event bus adapter ----> SSE/WebSocket projection
              |
              +----> S3/MinIO object storage for large I/O and logs
              |
              +----> usage ledger + price book
              +----> revenue ledger + allocation
              +----> rebuildable analytics projections
```

PostgreSQL is the truth for admission slots, current task/run/node state, checkpoints, usage, revenue, and audit. Financial correctness is based on append-only usage and revenue ledgers; every summary is rebuildable from those immutable entries. Temporal is the durable orchestration engine. Object storage owns large payloads. Redis may cache status or queue estimates, but it may not be the sole admission lock.

## Hard account-concurrency rule

The limit is account-wide, not browser-tab-wide and not tenant-membership-wide:

```text
effective runnable root tasks for account
= min(
    3,
    tenant quota remaining,
    tenant resource units remaining,
    platform/workload capacity,
    budget/provider quota
  )
```

Only root tasks consume one of the three account slots. Internal DAG nodes are governed by workload-specific worker concurrency and resource units. `PAUSED` and `WAITING_FOR_SLOT` do not consume an execution slot. A stale/unknown task releases a slot only after lease expiry and reconciliation policy permits it.

## Package contents

```text
.
├── .agents/skills/                 # 12 implementation Skills
├── docs/                           # product, architecture, state, database, FinOps, gates
├── sql/                            # PostgreSQL/Flyway-oriented reference migrations and queries
├── schemas/                        # Draft 2020-12 JSON Schemas
├── api/openapi.yaml                # control and analytics API contract
├── events/asyncapi.yaml            # task/progress/usage/revenue event contract
├── diagrams/                       # Mermaid source diagrams
├── examples/                       # schema-valid fixtures
├── tests/                          # acceptance, load, chaos, security, Python validation
├── scripts/                        # validation and packaging
├── install.sh
├── uninstall.sh
├── verify.sh
├── skill-manifest.json
└── skill-manifest.yaml
```

## Skills

1. `elmos-multitenant-task-finops-orchestrator`
2. `elmos-tenant-identity-rls`
3. `elmos-account-concurrency-admission`
4. `elmos-workload-aware-scheduler`
5. `elmos-task-lifecycle-temporal`
6. `elmos-task-progress-journal`
7. `elmos-checkpoint-recovery`
8. `elmos-task-io-artifact-archive`
9. `elmos-usage-metering-cost-ledger`
10. `elmos-revenue-margin-ledger`
11. `elmos-task-financial-analytics`
12. `elmos-concurrency-recovery-finops-certification`

The package contains **144 stable implementation tasks** in `docs/TASK-MATRIX.csv`.

## Recommended implementation order

```text
orchestrator
  → tenant identity / RLS
  → account admission slots
  → workload-aware scheduling
  → Temporal lifecycle
  → progress journal
  → checkpoint/recovery
  → input/output archive
  → usage/cost ledger
  → revenue/margin ledger
  → analytics
  → certification
```

## Key database rule

Never implement the three-task limit as:

```sql
SELECT count(*) ...;
-- then later
INSERT/UPDATE task ...;
```

That pattern oversubscribes under concurrent API replicas. Use the supplied three-slot table and atomic row locking/lease generation. The database migration contains reference functions for slot creation, claim, renewal, and release.

## Critical versus asynchronous persistence

Durable before acknowledgement:

- task state transitions;
- node completion/failure;
- checkpoint references;
- side-effect receipts;
- usage/cost entries;
- revenue entries;
- artifact manifests.

Asynchronous and batched:

- node heartbeats;
- fine-grained percentage deltas;
- verbose logs;
- non-critical telemetry;
- analytics rollups.

This split protects recovery and financial correctness without making every log line part of the workflow critical path.

## Cost model

```text
task_system_cost
  = model_cost
  + compute_cost
  + memory_cost
  + GPU_cost
  + runner/sandbox_cost
  + storage_cost
  + network_egress_cost
  + third_party_API_cost
  + allocated_shared_infrastructure_cost
  + explicit_correction_entries
```

Model cost records uncached input, cached input, output, embeddings, images, audio, and provider-specific units separately. The effective price and FX rate are snapshotted on each immutable usage event.

Human review effort and human-equivalent engineering time are reported separately and never silently mixed into autonomous system cost.

## Revenue and profitability

The ledger distinguishes:

- quoted value;
- billed/charged value;
- credits and refunds;
- recognized revenue;
- collected cash;
- payment fees and taxes;
- task/project revenue allocation.

Default profitability:

```text
gross_profit = recognized_revenue - posted_actual_system_cost
gross_margin = gross_profit / recognized_revenue
```

Every dashboard total carries scope, currency basis, recognition basis, and `as_of` time.

## Install

Codex:

```bash
./install.sh --codex
```

Claude Code:

```bash
./install.sh --claude
```

Custom target:

```bash
./install.sh --target /path/to/skills
```

## Verify

```bash
./verify.sh
```

The verification checks manifest integrity, stable unique task IDs, dependency order, Skill frontmatter and sections, JSON Schemas and examples, shell syntax, SQL contract markers, and package smoke installation.

## Production-claim boundary

This archive validates a specification and Skills package. It does **not** prove that an Elmos source repository has implemented PostgreSQL migrations, RLS, Temporal workflows, runner leases, task sandboxes, object storage, model/provider metering, payment reconciliation, load benchmarks, chaos recovery, or production gates. Those claims require repository-specific executed evidence produced by the certification Skill.
