# SQL conversion release status

## Decision

The repository is **not production-certified**. Repository-owned syntax, IR,
translation, local execution, and negative tests are bounded engineering
evidence only. They do not replace real vendor execution, an attested dedicated
Runner, or independent certification.

The machine-readable authority is `evidence/sql-route-closure-plan.json`:

- high-priority P0 route cells: `0` open;
- frozen source disposition: `1,910 / 1,910` units accounted for;
- automatic candidates: `1,390`; manual migration: `518` (`83` open);
- four-target common reachability: `1,213 / 1,390` admitted candidates;
- blocked route cells: `367` (P1/P2, preserved explicitly);
- real ChinaDB production execution: `0 / 13`;
- dedicated Runner 75 ms qualification: `NOT_RUN_ENVIRONMENT_INVALID`;
- independent verification: `NOT_RUN`;
- certification: `NOT_CERTIFIED`.

## Ordered path to production

1. Keep the P0 semantic workstream at zero regressions.
2. Supply an externally mounted DM8 Protocol 1.3.0 request with an exact product
   tuple, licensed disposable environment, credential references, vendor tools,
   signed authorization/execution receipts, raw evidence digests, and a separate
   operator-pinned Ed25519 trust store.
3. Run DM8 on an exclusively assigned, attested dedicated Runner. The p95 SLO
   remains 75 ms, host load must pass admission, and at most two measurement
   attempts are permitted.
4. Obtain independent verification and certification receipts from identities
   and organizations separated from implementer and executor.
5. Repeat the same exact process independently for the remaining 12 targets.

The repository cannot perform steps 2-5 without those external resources. It
must return `NOT_RUN` or `NOT_CERTIFIED` when they are absent.

## Commands

Prepare the checked-in request template:

```bash
cp engines/database-data-engine/sql-transpiler/examples/chinadb-production-qualification-draft.json /external/evidence/chinadb-request.json
```

Validate the DM8 pilot only after external systems have populated and signed the
request:

```bash
uv run --project engines/database-data-engine/sql-transpiler \
  python scripts/batch31/run_chinadb_qualification.py \
  --request /external/evidence/chinadb-request.json \
  --trust-store /external/trust/chinadb-trust-store.json \
  --require-target dm8 \
  --output /external/results/dm8-qualification-result.json
```

Validate all 13 targets:

```bash
uv run --project engines/database-data-engine/sql-transpiler \
  python scripts/operations/run_database_external_gate.py \
  --chinadb-request /external/evidence/chinadb-request.json \
  --chinadb-trust-store /external/trust/chinadb-trust-store.json \
  --expected-runner-attestation-digest "$ELMOS_PERFORMANCE_RUNNER_ATTESTATION_DIGEST" \
  --scope all
```

The protected manual workflow
`.github/workflows/chinadb-production-qualification.yml` applies the same byte
and Runner-attestation bindings on a self-hosted Runner labelled
`elmos-sql-perf-dedicated`.

Checked-in paths are rejected as external evidence, and neither command creates
keys, receipts, database results, performance measurements, or certification.
