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
- `engines/database-data-engine/sql-transpiler/examples/chinadb-production-qualification-draft.json`

Private keys are never request fields or repository artifacts. Signed
envelopes contain public identifiers, canonical payloads, and signatures;
external execution and verification systems retain their raw evidence under
the referenced content digests and applicable tenant policy.
