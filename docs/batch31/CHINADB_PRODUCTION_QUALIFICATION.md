# ChinaDB production qualification control plane

The ChinaDB runtime now has an executable path from bounded local handlers to
real target qualification without changing the current production evidence.
The current repository state remains:

- `externalExecution = NOT_RUN`
- `independentVerification = NOT_RUN`
- `certification = NOT_CERTIFIED`
- `targetSql = null`
- `productionDefinitionOfDoneCount = 0`

The count in this protocol has a denominator of 13 exact ChinaDB target
tuples. It is not raised by source parsing, generated SQL, a Boolean
`authorized` field, self-attested evidence digests, or local tests.
It qualifies target runtime/adapter tuples only; it does not promote any of
the 78 directional migration routes, which still require their own exact
source tuple, typed transformations, real workload evidence, and Batch 31
route gate.

## Qualification stages

Each target advances independently through these states:

1. `BLOCKED_INPUT`: exact tuple, disposable environment, vendor tools, or
   independent verifier is absent or invalid.
2. `BLOCKED_TRUST`: the input is complete but there is no operator-pinned,
   digest-matched Ed25519 trust store.
3. `READY_FOR_AUTHORIZATION`: the exact input digest can be submitted to the
   environment owner for authorization.
4. `READY_FOR_EXTERNAL_EXECUTION`: a trusted authorization binds the tenant,
   project, implementer, target tuple, environment, toolchain, operations, and
   validity window.
5. `READY_FOR_INDEPENDENT_VERIFICATION`: a trusted executor has signed real
   version/capability/render/apply/introspection/workload/reconciliation/
   performance/security/rollback/cleanup evidence with zero critical unknowns,
   differences, and test-integrity violations.
6. `READY_FOR_CERTIFICATION`: an independently trusted actor and organization
   have verified the raw evidence and physically separate holdout and
   representative-workload digests.
7. `PRODUCTION_DEFINITION_OF_DONE`: a separate certification authority has
   signed the exact verification chain and a non-expired decision. Its actor
   and organization must differ from the implementer, target executor, and
   independent verifier.

Invalid signatures, expired grants, tuple or digest drift, non-independent
actors, floating versions, production data, production-write scope, missing
operations, failed checks, or nonzero critical counters fail closed for that
target. Partial results are reported as partial and are not hidden by an
aggregate success rate.

The target qualification-input digest includes the protocol version and the
exact commercial capability-snapshot digest. A capability registry or protocol
change therefore invalidates earlier authorizations and every downstream
receipt instead of replaying evidence across a recertification boundary.

Protocol `1.2.0` requires two exact, role-specific digest sets in every
execution receipt. Artifact identity covers the source snapshot/catalog/data/
workload, target snapshot/release, canonical IR, transformation, compatibility
runtime, runner/toolchain, four physically separated corpora, data fixture,
query plan, target SQL candidate, acceptance profile, and gate result. Runtime
evidence separately covers version/capability probes, render/apply/introspection,
schema/type, query/routine, transaction, reconciliation, performance, security,
backup/restore, CDC, rollback, cleanup, and the raw evidence manifest. It also
requires a structured dedicated Runner summary: exclusive single-qualification
isolation, a verified host attestation, a monotonic high-resolution clock, five
warmups and 40 timed samples per query, normalized one-minute load no greater
than 1.0, at most two measurement attempts, and source and target p95 no greater
than the unchanged 75 ms SLO. An invalid or overloaded environment stays
`NOT_RUN_ENVIRONMENT_INVALID`; a signed Boolean `PASSED` cannot replace these
measurements. Missing, extra, malformed, or aliased digest roles fail closed.
The requirements command returns both exact field lists and the performance
contract for authorized external tooling.

## Exact input required for every target

The request contract requires all 13 catalog identities in deterministic
order. A completed target input contains:

- exact product identity, version, edition, compatibility mode, topology, provider,
  service tier, region, driver and driver digest;
- charset, collation, time zone, time-zone data version, SQL mode, extensions,
  and runtime artifact digest;
- an expiring disposable instance/schema or approved licensed sandbox using
  synthetic, masked, or separately approved snapshot data;
- opaque endpoint, credential, license, and resource references—never inline
  credentials;
- exact vendor tool versions and artifact digests covering version and
  capability probes, render, sandbox apply, introspection, workload execution,
  plan capture, backup/restore, CDC reconciliation, and cleanup;
- an independently contracted verifier whose actor and organization differ
  from the implementer.

## Commands

Generate current requirements and a 13-target draft:

```bash
uv run elmos-sql-transpiler commercial-production-requirements \
  --output /tmp/chinadb-production-requirements.json

uv run elmos-sql-transpiler commercial-production-template \
  --tenant-id TENANT \
  --project-id PROJECT \
  --actor-id IMPLEMENTER \
  --implementer-organization-id IMPLEMENTER_ORG \
  --output /tmp/chinadb-production-request.json
```

Populate the DM8 pilot slot from an operator-created, schema-valid input. The
merge is target-slot create-only: it rejects replacement of an existing tuple,
environment, tool set, verifier, or receipt. The input contains opaque secret
references, never credential values:

```bash
uv run elmos-sql-transpiler commercial-production-target-input-merge \
  /tmp/chinadb-production-request.json \
  /approved/dm8-production-target-input.json \
  --output /tmp/chinadb-production-request-dm8.json
```

Validate the input file against
`schemas/batch31/chinadb-production-target-input.schema.json`. The merge also
runs the runtime validators and will not create its output unless the exact DM8
tuple, unexpired disposable environment, complete vendor-operation coverage,
and independent verifier are valid. The other 12 target slots remain explicitly
`BLOCKED_INPUT` until the DM8 pilot and performance gate have passed.

Run the local blocker ledger without a trust store. Exit status `3` is
expected while the production definition of done is incomplete:

```bash
uv run elmos-sql-transpiler commercial-production-plan \
  /tmp/chinadb-production-request.json \
  --output /tmp/chinadb-production-plan.json
```

An operator may later supply a pinned public-key trust store. Both path and
digest are mandatory; request `trustStoreDigest` must match:

```bash
uv run elmos-sql-transpiler commercial-production-plan \
  /tmp/chinadb-production-request.json \
  --trust-store /approved/chinadb-trust-store.json \
  --trust-store-digest sha256:... \
  --output /tmp/chinadb-production-evaluated.json
```

After one target reaches `READY_FOR_EXTERNAL_EXECUTION`, generate its
secret-free Vendor Runner handoff. The artifact file must contain the exact 16
input digest roles returned by the requirements command:

```bash
uv run elmos-sql-transpiler commercial-production-execution-request \
  /tmp/chinadb-production-request.json \
  --trust-store /approved/chinadb-trust-store.json \
  --trust-store-digest sha256:... \
  --target-id dm8 \
  --input-artifact-digests /approved/dm8-input-artifact-digests.json \
  --output /tmp/dm8-vendor-execution-request.json
```

The handoff binds the authorization envelope, exact tuple, disposable
environment, vendor tools, input artifacts, operations, safety policy, and a
deterministic idempotency key. It contains opaque endpoint/credential
references only. Creating it performs no external call and leaves
`externalExecution = NOT_RUN`; the signed execution receipt remains the sole
way to advance that state.

DM8 is the enforced first target. A Vendor Runner handoff for any of the other
12 targets is rejected until DM8 has a complete authorization, external
execution, independent verification, and certification chain. Because protocol
1.2.0 makes the dedicated Runner 75 ms summary mandatory in the DM8 execution
receipt, this also enforces the rollout order `DM8 -> dedicated 75 ms gate ->
remaining 12 targets`; callers cannot bypass it by requesting another target
directly.

The internal read-only planning endpoints are:

- `GET /internal/v1/chinadb-production/requirements`
- `POST /internal/v1/chinadb-production/plan`

For the HTTP service, the trust store is an operator configuration, not a
request path. Configure both `ELMOS_CHINADB_QUALIFICATION_TRUST_STORE` and
`ELMOS_CHINADB_QUALIFICATION_TRUST_STORE_DIGEST`; the path must be absolute,
regular, non-symlinked, bounded, and digest matched.

The planner only verifies inputs and signed evidence. It never connects to a
database, runs a vendor binary, emits target SQL in its response, switches
traffic, writes production data, or issues a certificate.

## Contracts

- `schemas/batch31/chinadb-production-qualification-requirements.schema.json`
- `schemas/batch31/chinadb-production-qualification-request.schema.json`
- `schemas/batch31/chinadb-production-trust-store.schema.json`
- `schemas/batch31/chinadb-production-qualification-result.schema.json`
- `schemas/batch31/chinadb-production-target-input.schema.json`
- `schemas/batch31/chinadb-vendor-execution-request.schema.json`
- `engines/database-data-engine/sql-transpiler/examples/chinadb-production-qualification-draft.json`

Private keys are never request fields or repository artifacts. Signed
envelopes contain public identifiers, canonical payloads, and signatures;
external execution and verification systems retain their raw evidence under
the referenced content digests and applicable tenant policy.
