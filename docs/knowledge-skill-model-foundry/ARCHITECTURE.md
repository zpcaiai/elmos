# Architecture

```text
Pinned ZIP (untrusted data)
  -> read-only archive and checksum validator
  -> manifest-designated YAML contract compiler
  -> exact compiled-contract v2 catalog (41 meta + 1,310 atomic + 14 pipelines)
  -> authenticated policy gate
       -> 26 exact local semantic handlers
       -> 1,284 allowlisted prepare-only handlers (no semantic effect)
       -> exact Broker route + request-bound permit + durable idempotency
  -> tenant-private CAS + durable SQLite transition/outbox/checkpoint/evidence
  -> unsigned local evidence bundle
  -> external independent verifier/signature/certification gate
```

## Trust boundaries

The importer validates path normalization, duplicate and Unicode collisions,
entry modes, compression limits, checksums, schemas, per-Skill inventories,
evaluation counts, and dependency acyclicity without importing source code. The
archive's Markdown, Rego, SQL, CI and Python files have no runtime authority.

Execution context is derived from a host-minted identity and binds tenant,
project, actor, purpose, environment, workspace, revision and a short-lived
capability lease. Missing or ambiguous identity fails before an execution row,
artifact, adapter, outbox event, or evidence receipt is created.

## Runtime layers

1. The compiled catalog binds exact names, all six authoritative source
   documents per Skill, typed inputs/outputs, dependencies, permissions, gates,
   handler IDs, execution contracts, and evidence ceilings.
2. The 26 local semantic handlers reject missing or empty declared inputs and
   produce exactly the declared output set. All other handlers materialize only
   deterministic contracts and plans; they do not impersonate compilers,
   databases, clouds, trainers or signers.
3. External execution accepts no direct callable. A host-owned Broker binds an
   exact adapter and non-executable route to Skill set, version, digest, effect
   class, payload, operation, purpose, tenant, project, actor, environment,
   workspace, revision, expiry and a one-time invocation permit. A successful
   result requires a verified provider receipt and the exact declared output
   set. Unknown external outcomes remain unreconciled and cannot be retried
   automatically.
4. The store provides scoped idempotency, legal transitions, checkpoints,
   immutable events/evidence, and an outbox for externally reconciled effects.
5. The CAS is private, immutable and digest verified. Raw customer content is
   never written to logs or global caches.

The six asset classes—knowledge, Skill contract, experience, dataset,
model/adapter release and evidence—remain distinct and separately governed.
Knowledge, experience, dataset, model and serving helpers are bounded
process-local preparation surfaces; only the injected SQLite/CAS control path
provides persistence. They must not be represented as production asset stores.
