# ETGB signed external Harness protocol

The repository runtime implements the caller side for all seven non-local ETGB
adapter families:

- `external-transformation-harness`
- `external-repository-translation-harness`
- `external-project-generation-harness`
- `external-project-evolution-harness`
- `external-requirement-reasoning-harness`
- `external-dual-database-harness`
- `external-fault-injection-harness`

The remote service is separately deployed and authorized. A configured endpoint
does not prove that the service exists, that a case ran, or that a release is
certified.

## Administrative configuration

Configuration is strict JSON with exactly `schema_version`, `trust_store`,
`policy`, and `adapters`. Endpoints must use HTTPS; HTTP is permitted only for
explicit loopback testing. URL credentials, query strings, fragments, redirects,
and undeclared adapters are rejected. `auth_token_env` and `client_key_env` are
references, not secret values. The trust store contains public keys only, and
each worker key must include `record_types: ["adapter-execution"]`.

Use [`harness-config.example.json`](harness-config.example.json) as a structural
example. `harness-preflight` returns `READY_FOR_EXTERNAL_EXECUTION_CONFIG` only
when all seven adapters are configured; it still returns `NOT_CERTIFIED`.

## Request binding

Every request contains the full case document and seed plus these exact bound
fields: tenant, project, task, run, case-run, frozen candidate digest, full plan
digest, case digest, environment, authority, owner, fencing token, idempotency
key, and checkpoint digest. The request itself has a canonical SHA-256 digest.
A shard worker must use the same frozen plan and candidate as every other worker.
The full release has 46,664 distinct cases and 131,452 required `(case_id, seed)`
executions; 131,448 executions use one of the seven external adapters.

Example worker invocation:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . run --profile release \
  --plan .elmos/etgb/release-plan-v11.json --shard-id 0 \
  --candidate .elmos/etgb/frozen-candidate-v11.json \
  --harness-config /secure/admin/etgb-harness.json \
  --tenant-id tenant-a --project-id project-a --task-id release-campaign-a \
  --environment-id isolated-env-a --authority-id authority-a \
  --owner worker-a --fencing-token 1 \
  --checkpoint-digest sha256:<checkpoint-digest> \
  --state-db .elmos/etgb/state/shard-0.sqlite \
  --artifact-root .elmos/etgb/evidence/release \
  --license-reviews /secure/reviews/license-reviews.jsonl \
  --trust-store /secure/reviews/release-trust-store.json \
  --output .elmos/etgb/results/shard-0.jsonl
```

After all shards complete, use `merge-results` with every shard file, the same
plan and candidate digest, and the worker public-key trust store. The merger
requires the exact 131,452 case-run partition, rejects duplicates or omissions,
recomputes immutable case digests, re-verifies every external signature and
binding, and emits an atomic canonical result file plus merge receipt.

## Signed response

The endpoint returns an Ed25519 signed record of type `adapter-execution`. Its
payload binds the exact request digest, adapter, and all execution-context
fields; reports `passed`, `failed`, `error`, or `unavailable`; includes at least
one typed oracle; binds a manifest digest and artifact digests; and reports
non-negative cost fields. A `passed` response with any failed critical oracle is
rejected as a Harness defect.

The runtime stores the canonical request, signed response, and signature
verification result. A transport failure may retry only when classified as
transient, and every retry reuses the exact body and idempotency key. Semantic,
authorization, protocol, signature, digest, and critical-oracle failures do not
retry.

The local phase runtime also validates the adapter contract before changing
run state. Each adapter must implement `prepare`, `baseline`,
`transform_or_generate`, `build`, `validate`, `score`, `publish`,
`compensate`, and `cleanup`. A successful phase must return every contract
output, valid content digests, regular-file artifact references, non-negative
usage, and JSON-serializable raw data. Raw phase results are persisted before
their checkpoint is written, and the checkpoint binds the workspace, artifact
digests, and side-effect receipts. The contract can be checked without
executing an adapter:

```bash
PYTHONPATH=engines/etgb-engine/src python3 -m elmos_etgb \
  --repo-root . harness-contract
```

## External evidence boundary

Local protocol tests use ephemeral keys and an in-process simulated transport.
Those tests prove request/response enforcement only. Real transformations,
databases, project generation, evolution, fault injection, production
environments, independent verification, and release certification remain
`NOT_RUN` / `NOT_CERTIFIED` until their signed evidence is supplied.
