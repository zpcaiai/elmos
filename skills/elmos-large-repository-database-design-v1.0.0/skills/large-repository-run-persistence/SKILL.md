---
name: large-repository-run-persistence
description: Design, implement, migrate, test, operate, or review Elmos PostgreSQL persistence for large-repository project generation and cross-repository/language conversion. Covers tenant-safe admission, exactly-three account task slots, durable Job/Run/Task/Attempt state, append-only events, sessions, checkpoints, CAS artifacts, repository/IR/capability indexes, generation/transformation ledgers, P05 evidence gates, model/tool/cost/ETA metering, side-effect reconciliation, RLS, partitioning, retention, migrations, CI and recovery.
license: Proprietary
compatibility: codex, claude-code, opencode, deepseek-harness, openharness, postgres-16, postgres-17
metadata:
  product: elmos
  package: deployment-and-data-plane
  phase: DB-1-DB-4
  version: 1.0.0
---

# Elmos Large Repository Run Persistence

## Mission

Build a commercial-grade database data plane that lets Elmos run very large project-generation and repository-conversion jobs for hours or days while remaining:

- resumable after browser, process, node, scheduler, database, or network failures;
- tenant-isolated;
- idempotent under duplicate requests and messages;
- protected from stale Worker writes by fencing;
- measurable for Token, compute, storage, cost, revenue and machine ETA;
- complete only when P05 validates exact revisions and sealed evidence;
- able to learn only from verified and explicitly authorized data.

## Non-negotiable architecture

```text
PostgreSQL = business truth
Temporal   = durable control flow
CAS        = large immutable bytes
Redis      = transient acceleration only
```

Never move admission authority, completion authority, finance ledgers or external side-effect truth into Redis or an in-memory Scheduler.

## Storage boundary

### Store in PostgreSQL

- Tenant, Account, Project, Repository;
- Job, Submission, Input Revision;
- Run, Stage, Task, Dependency, Attempt, Lease/Fence;
- current state + append-only Run/Session Events;
- Workspace, Workpad, Approval, Human Gate, Control Request;
- Checkpoint and component manifests;
- Artifact/CAS metadata and links;
- file/module/symbol/runtime-surface indexes;
- graph/IR shard references;
- Requirement/Capability ledger;
- generation/transformation plans and units;
- verification results, semantic gaps, evidence and gates;
- model/tool invocations, ledgers, budgets, ETA and cache facts;
- Outbox/Inbox, side-effect receipts, compensation and reconciliation;
- learning authorization, cases, rules and benchmark results;
- release, migration, service health, deployment checks/gates;
- audit.

### Store in CAS

- repository archives and source file bodies;
- complete AST/CFG/DFG/call graph/IR;
- large model outputs;
- build/test stdout and traces;
- generated repository trees and patches;
- screenshots/videos/reports/SBOM/signatures;
- evidence raw payloads;
- archives.

Database rows carry artifact id, digest, size, state, URI metadata and bounded summaries.

## Required flow

```text
Submission
  → Idempotency
  → Atomic Account Slot Claim
  → Job
  → Run with immutable revision binding
  → Run Stages
  → Task DAG
  → Task Attempt + Lease/Fence
  → Ordered Events + Session
  → Artifact staging/publish
  → Checkpoint seal
  → Repository intelligence
  → Generation/Transformation
  → Verification/Repair
  → Evidence bundle
  → P05 gate
  → Atomic completion + outbox + slot release
```

## Exactly-three task slots

Each account owns exactly three `core.account_task_slot` rows. `concurrency_limit` may be 0–3, but physical rows remain 1, 2, 3.

Use `core.claim_account_slot`, `renew_account_slot`, `release_account_slot`.

Never:

```text
SELECT count(active jobs)
then INSERT a run
```

That is race-prone.

Every claim increments `lease_generation`; all renew/release operations verify the current generation and owner token.

## Job and Run identities

A Job is the user-visible goal. A Run is one execution bound to exact immutable revisions:

```text
source_repository_revision
baseline_repository_revision
target_repository_revision
requirements_revision
policy_revision
workflow_revision
model_route_revision
toolchain_revision
environment_revision
archetype_revision
```

Do not mutate these fields after work begins. A changed baseline creates a new Run or explicit superseding Revision.

## Task DAG

A Task is a stable work unit, not a Worker process. Persist:

- task key/type/title;
- stage;
- hard/soft dependencies;
- input hash;
- expected output contract;
- skill/agent/model preference;
- resource class;
- priority;
- timeout/retry policy;
- current attempt/checkpoint/output manifest;
- status.

A TaskAttempt records one execution. Do not overwrite the previous attempt.

## Lease and fencing

Every active Attempt has:

```text
lease id
owner token
lease generation
expiry
worker id
fencing token
```

Claiming after expiry increments generation. Finish/Artifact publish/Checkpoint writes must validate the current generation. A stale Worker receives `STALE_FENCE` and must discard its output.

## State and events

Keep current state tables for querying and append-only events for replay/audit.

State transition, event, outbox and financial reservation must be committed in the same database transaction.

Run and Session Events have:

- per-aggregate sequence number;
- previous event hash;
- event hash;
- bounded JSON payload;
- optional Artifact reference for large content.

Any model-visible fact must be reconstructable from Session Event history.

## Context compaction

Persist Context Epoch, compaction input/output boundaries, summary Artifact, token reduction and preservation metadata. Compaction never deletes audit history; it changes projected model history.

## Artifact lifecycle

```text
reserved/writing
→ staged/sealed
→ CAS promoted
→ available/published
```

Never mark an Artifact available until the CAS object exists and its hash/size have been verified.

A sealed Manifest is immutable. Changes create a new Manifest.

## Checkpoint

A sealed Checkpoint references a sealed Manifest and components such as:

- repository scan;
- Semantic IR;
- requirement/generation/transformation plan;
- workspace snapshot;
- Session event boundary;
- side-effect cursor;
- usage cursor;
- output tree;
- toolchain/environment fingerprint.

Recover only from compatible sealed Checkpoints. Incomplete checkpoints are ignored or quarantined.

## Repository intelligence

For each source revision persist:

- file catalog;
- modules/build targets/dependencies;
- symbols;
- runtime surfaces;
- graph shard references;
- Semantic IR revision and shards;
- capabilities and edges;
- unsupported semantics;
- discovery warnings and analysis snapshot.

For very large repositories, batch with COPY/staging and store full graphs/IR in CAS shards. Database File/Symbol metadata must stay bounded.

## Generation and transformation

Persist traceability:

```text
Requirement
→ Architecture
→ Plan
→ Unit
→ Capability Mapping
→ Generated File / Transformation Unit
→ Rule Application
→ Target Revision / Patch Set
→ Verification
→ Evidence
```

No “module completed” state without corresponding requirement/capability mapping and evidence status.

## External side effects

Before Git push, PR creation, tracker mutation, deployment, migration or other write, reserve a stable idempotency key in `integration.side_effect_receipt`.

Timeout after dispatch becomes `unknown_result`, not failed. Reconcile provider state before retrying. P05 refuses completion while unresolved side effects exist.

## Metering

Record every model round and tool execution, including failures and intermediate rounds.

Keep:

- provider/model/route/endpoint;
- price snapshot;
- input/output/reasoning/cached tokens;
- latency/throughput;
- retry/fallback/escalation;
- tool approval/timeout/concurrency;
- compute/storage/network resource usage;
- immutable usage/cost/revenue ledgers;
- budget reservations;
- cache savings.

ETA fields must remain separate:

```text
machine wall-clock p50/p90
machine wall-clock remaining p50/p90
expected HITL wait
human-equivalent p50/p90
```

Never present human engineering days as system execution ETA.

## P05 completion authority

The Agent cannot mark a Run completed. The application cannot directly update `exec.run.status='completed'`.

Only `verify.complete_run_with_gate` may complete a Run after rechecking inside its transaction:

- exact revision binding;
- sealed evidence bundle;
- evidence not foreign/revoked/stale;
- authoritative requirement and capability coverage;
- critical requirements;
- required suites;
- no unfinished tasks;
- no open high/critical/unknown semantic gaps per policy;
- no unresolved side effects;
- correct current target revision.

The same transaction completes Run/Job, appends event/outbox and releases account slot.

## Deployment completion authority

Only `ops.complete_deployment_with_gate` may mark a deployment healthy after:

- required checks pass;
- required release components report live/ready;
- observed image digests match release digests;
- required migration succeeded;
- deployment P05/smoke/security evidence exists.

## Tenant isolation

Every commercial table except the root tenant row carries `tenant_id`.

Enable and FORCE RLS. Use:

```sql
BEGIN;
SET LOCAL app.tenant_id = '...';
SET LOCAL app.actor_id = '...';
SET LOCAL app.request_id = '...';
```

No context must fail closed. Use security-invoker/security-barrier views. Application roles must not be owner, superuser or BYPASSRLS.

## Roles and credentials

Use separate roles for migration, control API, scheduler, runtime, router, analyzer, transformer, verifier, learning, readonly ops, audit and backup.

Workers should not connect directly to the control database. Prefer short-lived scoped Run Tokens and host-side APIs/functions. Long-lived Provider/Git/Cloud/DB secrets never enter Agent child environments.

## Partition and retention

Initial high-write tables use 16 Hash partitions. Add time subpartitions when partitions reach operational thresholds.

Retention levels:

```text
R0 transient 1–7d
R1 active 30d
R2 product/debug 90–180d
R3 commercial evidence 1–3y
R4 compliance/finance 5–10y or policy
```

Evidence, certification, finance and audit outlive ordinary temporary Run data.

## Implementation order

### DB-1 Durable Execution Core

Implement and test first:

- tenancy/projects/jobs/submission;
- exact three slots;
- Run/Stage/Task/Attempt/Lease;
- events/session/workpad/control;
- Artifact/Manifest/Staging;
- Checkpoint;
- Outbox/Inbox/Side-effect;
- model/tool/cost/ETA core;
- audit/RLS;
- transaction functions.

Exit gate: disconnect/restart/failover/fencing/idempotency tests pass.

### DB-2 Repository Intelligence

Implement File/Module/Symbol/Runtime Surface/Graph/IR/Capability and cache.

Exit gate: large benchmark repositories scan incrementally and no source/IR body enters PostgreSQL.

### DB-3 Generation, Transformation, Verification

Implement requirement graph, architecture/generation/transform plans, Coverage, Evidence, P05 Gate and Repair.

Exit gate: a complete benchmark run can only finish through P05 and produces a sealed Evidence Bundle.

### DB-4 Learning and Operations

Implement authorization, curated cases, repair traces, rules, benchmarks, release, migration, health and deployment gates.

Exit gate: unapproved tenant data never appears in learning assets and deployments only become healthy through the deployment gate.

## Required implementation files

Use this package as source:

- `database/migrations/V001__...sql` through `V090__...sql`;
- `database/TABLE-CATALOG.md`;
- `database/queries/operator_queries.sql`;
- `database/tests/invariants.sql`;
- `database/tests/concurrency-scenarios.md`;
- `docs/DATABASE-DESIGN-LARGE-REPOSITORY-RUNS.md`;
- `docs/DATABASE-TRANSACTION-AND-RECOVERY.md`;
- `docs/DATABASE-PARTITIONING-RETENTION.md`;
- `docs/DATABASE-SECURITY-RLS.md`;
- `docs/DATABASE-MIGRATION-OPERATIONS.md`.

## CI requirements

Run:

```text
static database design validator
PostgreSQL 16 empty migration
PostgreSQL 17 empty migration
previous GA → latest migration
invariants.sql
RLS two-tenant tests
slot/idempotency concurrency tests
lease/fence stale-writer tests
event concurrency/hash tests
failover/retry tests
P05/deployment gate negative and positive tests
```

## Completion checklist

Do not declare this skill implemented until:

- [ ] all migrations execute on real PostgreSQL 16/17;
- [ ] no FK/constraint/RLS drift;
- [ ] exactly-three-slot race test passes;
- [ ] stale Worker cannot write;
- [ ] Run/Session Event chains are reconstructable;
- [ ] checkpoint crash recovery passes;
- [ ] CAS staging cannot expose missing objects;
- [ ] `unknown_result` blocks P05;
- [ ] revoked/stale evidence blocks P05;
- [ ] completed Run always has exact passing Gate;
- [ ] machine ETA differs from human-equivalent time;
- [ ] cost/revenue ledgers reconcile;
- [ ] dual-tenant RLS test passes;
- [ ] Learning requires active authorization;
- [ ] deployment migration/health/image digest gate passes;
- [ ] backup restore and migration replay exercise succeeds.
