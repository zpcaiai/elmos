# Architecture

```text
Pinned ZIP (untrusted data)
  -> read-only archive and checksum validator
  -> manifest-designated YAML contract compiler
  -> exact compiled-contract v2 catalog (41 meta + 1,310 atomic + 14 pipelines)
  -> authenticated policy gate
       -> 66 exact local semantic handlers
       -> 1,244 exact native programs and distinct host-routed bindings
       -> exact Broker route + request-bound permit + durable idempotency
       -> 14 exact pipeline Broker routes with the same fail-closed boundary
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
2. The 66 local semantic handlers reject missing or empty declared inputs and
   produce exactly the declared output set. Each of the other 1,244 identities has an exact seven-stage native program plus a
   unique adapter ID, operation, digest and route derived from its exact source
   and runtime contract. These bindings do not impersonate compilers,
   databases, clouds, trainers or signers when the host integration is absent.
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
6. Every golden pipeline has a distinct privileged Broker binding. The runtime
   can build the exact request a trusted host uses to issue a permit, then
   requires complete outputs and a verifier-bound provider receipt. Default
   construction has no Broker and therefore performs no pipeline effects.

The six asset classes—knowledge, Skill contract, experience, dataset,
model/adapter release and evidence—remain distinct and separately governed.
Knowledge, experience, dataset, model and serving helpers are bounded
preparation surfaces with optional injected SQLite persistence. The v2 asset
schema retains creation identities and versioned current state, authenticates
scope and commits state changes with audit events in one transaction. Serving
availability is fenced by gateway instance and time. Uninjected or in-memory
stores remain process-local; production/provider qualification is still open.
