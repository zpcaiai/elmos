# SQL conversion release status

## Decision

The repository release gate is now evidence-derived and fail-closed. The only
frozen migration-pilot route is SQLite 3.53.3 public-domain/Python 3.14.6 to
PostgreSQL 17.5 Community/psql 17.5. It remains `experimental`, is not release
eligible, and is not certified. The 13 ChinaDB targets remain a bounded
preflight surface; compatibility-mode syntax emission is not vendor-runtime
equivalence.

The exact launch tuple is machine-readable in `sql-line-launch-scope.json`.
Adding a second or third launch route requires an independent pack and the same
exact-tuple, evidence-digest, real-engine, rollback, and gate controls.

## P0 baseline

- 81 migration files and 1,739 statements were rescanned on 2026-09-04.
- 1,302 statements are automatic candidates, 435 require manual migration,
  two require source-format review, and scanner engine defects are zero.
- Every statement and all 22,607 ChinaDB target-route units have an explicit
  disposition. ChinaDB target SQL emissions in this ledger remain zero.
- Strict four-target reachability is 363/1,302. Per-target upper bounds are
  PostgreSQL 1,302, SQL Server 525, Oracle 435, and MySQL 411.
- The checked-in summary records the raw report digests and replay commands in
  `evidence/sql-corpus-scan-summary.json`.
- `evidence/sql-target-reachability.json` records all 1,302 admitted units and
  their four target outcomes. The derived closure plan accounts for all 5,208
  route cells: 2,673 are syntax-emittable and 2,535 remain blocked across 33
  target/blocker workstreams. Runtime-verified cells remain zero.
- Batch 31 pack validation executes formal JSON Schemas. Certification status
  is derived from evidence, role separation, lifecycle state, and content
  digests. A self-reported `certified` value cannot promote a pack.
- CI runs the Batch 31 toolkit and every checked-in database pack. The separate
  release gate exits nonzero until independently evidenced `limited` or
  `certified` status is derived.

## P1 implementation boundary

- The launch route has a repository-owned pack, exact local source and target
  runners, typed canonical IR, capability checks, source/target apply and
  introspection, normalized errors, real plans, transaction/locking checks,
  independent corpus directories, and digest-bound evidence.
- `build_manual_review_backlog.py` materializes every manual item as a stable,
  ownerable record with implementation strategy, waiver, expiry, artifact, and
  revalidation fields. `--require-closed` fails while any item is unresolved.
  The current backlog contains 435 open items and therefore blocks broad-route
  release claims.
- The Java database worker now supports an optional owner-only, atomically
  written durable store for terminal jobs and idempotency records, and the
  production Compose profile mounts that store. Restart recovery of terminal
  state is covered locally. Live-operation checkpoints/resume, distributed
  coordination, production credential leases, and actual vendor adapters are
  not claimed by this local pilot.

## P2 implementation boundary

- The local SQLite-to-PostgreSQL reference executes a checkpointed initial
  load, an offline delete delta, detailed reconciliation, constraint and
  transaction negatives, source read-only-session enforcement, target backup
  and restore, and an offline cutover rehearsal on disposable synthetic data.
- Online CDC, a production writer switch, customer backup/restore, production
  rollback and DR, external SLO/alert/on-call operation, data residency review,
  pilot acceptance, independent verification, and certification remain
  `NOT_RUN` / `NOT_CERTIFIED`. They require external systems, accountable
  organizations, credentials, and approvals and cannot be manufactured by a
  repository change.
- Performance qualification retains the exact 75 ms p95 SLO and at most two
  bounded attempts. A host must explicitly opt in and pass normalized-load
  preflight; otherwise the timing state is `NOT_RUN_ENVIRONMENT_INVALID` and
  the release gate remains closed.

## Release commands

```bash
make b31-skills-test b31-all-packs-check
make b31-release-gate PACK=sqlite-3-53-3-to-postgresql-17-5
```

The first command is the engineering gate. The second is the production release
gate and is expected to fail closed until the external evidence above exists.
