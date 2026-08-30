# Elmos PI Harness 5.1

This is the repository-owned implementation of the executable core described by
`elmos-pi-harness-architecture-v5.1.0.zip`.  The ZIP is retained as untrusted
source material; its installers, scripts, SQL, prompts, and workflow documents
are not executed by this implementation.

The exact source archive is pinned to SHA-256
`8d600342ab0652e23aef80ef72583dfa4cbe01db7dc49b7d339dd40aa285c75c`
(425,097 bytes). `make pi-harness` validates that identity and the complete
repository-owned implementation surface before running package tests.

Implemented runtime guarantees:

- environment/attachment-owned authority snapshots with upper-policy intersection;
- explicit tenant and actor context, tenant-scoped durable reads and writes;
- append-only task events, bounded replay, idempotency, branch, pause/resume/cancel;
- executor replacement and generation fencing for callbacks and tool results;
- durable workspace ownership, heartbeats, and checkpoint-gated stale takeover;
- typed tool results (text/media/encrypted/unknown) without adapter stringification;
- protocol/schema negotiation and adapter boundary types;
- content-addressed artifact storage with atomic writes;
- provider-neutral benchmark campaigns where only an external verifier can set success;
- conservative evidence decisions that never manufacture certification.

Production-facing code surfaces are also implemented:

- PostgreSQL 16+ pooling, checksum-locked migrations, transaction-local tenant
  RLS, full kernel-store parity, and managed S3/KMS artifact storage;
- Temporal TLS client/worker, deterministic pause/cancel/resume signals,
  durable idempotent activity replay, bounded retry, generation fencing, and
  history replay;
- exact-target cloud operation journal, separate approval, provider-native
  evidence, `UNKNOWN` reconciliation, rollback, destroy, and orphan handling;
- OIDC/JWKS plus verified mTLS SPIFFE tenant/project identity binding, CRL
  enforcement, and no authoritative caller-supplied tenant header;
- independent Ed25519 verifier trust store, signed UAT, encrypted backup and
  isolated restore rehearsal, and canary/promotion/rollback deployment control.

Run locally:

```bash
python3 -m pip install -e 'packages/pi-harness[production,dev]'
make -C packages/pi-harness test
make -C packages/pi-harness typecheck
make -C packages/pi-harness demo
PYTHONPATH=packages/pi-harness/src python3 -m elmos_pi_harness.cli qualification-status
```

Install real adapters with `pip install '.[production]'`. PostgreSQL schema
migration is explicit and checksum locked:

```bash
elmos-pi-harness postgres-migrate \
  --database 'service=pi_harness_migration' \
  --migration-root /absolute/path/to/packages/pi-harness/sql
```

External qualification uses a frozen-release, append-only evidence ledger.
It content-addresses raw outputs and separates execution, independent
verification, customer/release acceptance, and certification authority:

```bash
elmos-pi-harness qualification-init \
  --ledger-root /absolute/immutable/ledger \
  --release-manifest /absolute/input/release-candidate.json
elmos-pi-harness qualification-status \
  --ledger-root /absolute/immutable/ledger \
  --trust-store /absolute/trust/verifier-trust-store.json
elmos-pi-harness qualification-archive \
  --ledger-root /absolute/immutable/ledger \
  --configuration /absolute/config/immutable-evidence-s3.json \
  --authorization-id '<approved-archive-operation>' \
  --actor-id '<archive-workload-identity>'
```

See [EXTERNAL_QUALIFICATION_RUNBOOK.md](docs/EXTERNAL_QUALIFICATION_RUNBOOK.md)
for the exact one-by-one procedure and machine-readable schemas. The operator
always emits `certified:false`; its maximum decision is
`READY_FOR_HUMAN_DECISION`, which still requires external release authority.

The standard-library HTTP server remains suitable for a single-node controlled
deployment. The production profile disables static API tokens and requires
OIDC plus direct TLS client-certificate verification, PostgreSQL, Temporal and
a managed object store. Private IdP trust is configured explicitly with an
absolute, non-symlink `--oidc-jwks-ca` path (or `ELMOS_PI_OIDC_JWKS_CA`), so
JWKS verification does not depend on a previously cached process-global TLS
context. Code availability does not prove those systems were run: real
cloud/IdP/Temporal/DR/customer/deployment and independent evidence remain
`NOT_RUN`; certification remains `NOT_CERTIFIED`.
