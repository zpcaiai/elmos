# Durable Runtime, Observability and FinOps

## Run lifecycle

```text
QUEUED → RUNNING ↔ PAUSED
             │         │
             ├→ BLOCKED│
             ├→ FAILED │
             ├→ CANCELLING → CANCELLED
             └→ COMPLETED (not automatically CERTIFIED)
```

State transitions are commands validated against current execution epoch and policy. A worker heartbeat cannot declare completion.

## Work and fencing model

A step attempt includes:

- `run_id`, `step_key`, `attempt`;
- lease owner and expiry;
- lease generation;
- fencing token;
- idempotency key;
- authority snapshot;
- input/output hashes;
- checkpoint;
- side-effect reconciliation state.

All writes compare the current generation/token. A stale worker can finish computation but cannot commit results.

## Checkpoint and replay

Checkpoints include semantic state, pending work, approvals, provider/session references, generated repository tree hash and side-effect ledger references. They must be:

- versioned and schema-migratable;
- encrypted/access-controlled;
- content-addressed;
- bound to RevisionSet and execution epoch;
- verified before resume;
- invalidated when target/model/tool semantics make replay unsafe.

Provider-native conversation state may be referenced but cannot be the only recoverable state.

## Side-effect reconciliation

For each effect:

```text
PROPOSED → APPROVED → EXECUTING → APPLIED → RECONCILED
                                    └──────→ UNKNOWN/BLOCKED
                         compensation ─────→ COMPENSATED
```

After worker/network failure, a reconciler queries the authoritative external system using the idempotency key or external operation ID. `UNKNOWN` blocks completion.

## Scheduling and concurrency

The default account concurrency remains three top-level tasks unless product policy overrides it. Scheduler concerns:

- tenant/account quotas;
- target adapter and environment capacity;
- provider rate limits;
- priority/fairness;
- memory/context size;
- verifier cost;
- network/data residency;
- worktree conflicts;
- backpressure and load shedding.

Parallelism is used only when dependency, workspace and semantic merge boundaries are explicit.

## Machine wall-clock ETA

ETA is a machine-run estimate, not an engineer-day estimate. Record:

- queue time;
- setup/build time;
- model/tool execution;
- verifier phases;
- repair cycles;
- human approval wait separately;
- external service wait;
- checkpoint/recovery overhead.

The API exposes point estimate and interval plus confidence and assumptions. Accuracy is measured by phase, adapter, repository size/risk and model route.

## FinOps ledger

Each run records:

- input/output/cached tokens;
- provider/model;
- compute seconds and accelerator class;
- storage and artifact bytes;
- vector/index operations;
- network egress;
- third-party tool charges;
- sandbox/runner time;
- estimated and actual amount;
- cache savings;
- customer credit/revenue allocation.

Budget enforcement operates before requests and at phase boundaries. A repair loop cannot overdraw budget without an approved revision.

## OpenTelemetry model

Recommended span hierarchy:

```text
goal.run
 ├─ spec.compile
 ├─ source.import
 ├─ ai_sir.compile
 ├─ target.negotiate
 ├─ target.generate[target=dify]
 ├─ target.generate[target=langgraph]
 │   ├─ lower
 │   ├─ emit
 │   ├─ native.build
 │   └─ native.start
 ├─ verification.differential
 ├─ verification.security
 └─ certification.evaluate
```

Attributes include tenant-safe identifiers, RevisionSet, adapter/version/digest, model/provider, tool, authority decision, proof obligation, cost and machine time. Sensitive payloads are referenced by evidence ID rather than logged.

## SLOs

Illustrative product SLOs must be customer/profile-specific:

- control API availability;
- queued-to-start time;
- checkpoint recovery success;
- stale-worker rejection;
- unreconciled side effects;
- tenant isolation violations;
- evidence completeness;
- adapter native-conformance pass;
- machine ETA MAPE;
- cost-accounting gap;
- certification reproducibility.

No universal number is hard-coded into this package.

## Cache layers

- immutable source/artifact CAS;
- compiler/semantic IR cache;
- adapter lowering/emission cache;
- dependency/build cache;
- model prefix/provider cache;
- retrieval/index cache;
- verifier/proof cache.

Keys include semantic inputs and policy/tool/adapter versions. Drift invalidates only affected layers, but proof cache reuse requires claim, assumptions, verifier digest and evidence freshness to match.

## Operational endpoints

Generated services expose, where applicable:

- `/livez`
- `/readyz`
- `/metrics`
- `/version`
- structured health for database, event bus, artifact store, policy, adapter workers and certifier.

Readiness does not mean E5; it means the instance can serve within its runtime contract.
