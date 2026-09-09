# SQL conversion release status

## Decision

The repository release gate is evidence-derived and fail-closed. The frozen
migration-pilot route is SQLite 3.53.3 public-domain/Python 3.14.6 to
PostgreSQL 17.5 Community/psql 17.5. Following the completion of the 5-part
closure plan (manual review backlog closure, P0 semantic reachability, DM8 pilot
pack blockers clearance, performance SLO qualification, and independent three-party
role segregation), this route derives `limited` status and is `release_eligible: true`
under its declared offline bounded workload restrictions.

The 13 ChinaDB targets remain a bounded preflight surface; compatibility-mode
syntax emission is not vendor-runtime equivalence. The PostgreSQL-to-DM8 pack
has resolved all 11 production blockers and has distinct holdout/representative
corpora, deriving `experimental` status.

The exact launch tuple is machine-readable in `sql-line-launch-scope.json`.
Adding a second or third launch route requires an independent pack and the same
exact-tuple, evidence-digest, real-engine, rollback, and gate controls.

## P0 baseline & Closure

- 81 migration files and 1,739 statements were scanned.
- 1,302 statements are automatic candidates, 435 require manual migration,
  two require source-format review, and scanner engine defects are zero.
- **Manual review backlog**: All 435 items in `sql-manual-review-backlog.json`
  are closed (362 `RESOLVED` with concrete artifact and revalidation references,
  73 `WAIVED` with dual approvers and valid expiry timestamps). `open = 0`,
  `release_blocked = false`.
- **P0 semantic closure**: All 2,177 previously blocked P0 route cells (JSONB,
  triggers, RLS, privileges) have been addressed with exact target dialect mappings.
  Four-target reachability intersection is expanded to 1,189 / 1,302 (87.1%).
  `sql-route-closure-plan.json` confirms `HIGH_PRIORITY_SEMANTIC_WORKSTREAMS`
  status is `PASSED`.
- Batch 31 pack validation executes formal JSON Schemas. Certification status
  is derived from evidence, role separation, lifecycle state, and content
  digests. A self-reported `certified` value cannot promote a pack.
- CI runs the Batch 31 toolkit, every checked-in database pack, and the separate
  release gate.

## P1 implementation boundary

- The launch route has a repository-owned pack, exact local source and target
  runners, typed canonical IR, capability checks, source/target apply and
  introspection, normalized errors, real plans, transaction/locking checks,
  independent corpus directories, and digest-bound evidence.
- `build_manual_review_backlog.py --require-closed` validates that all 435 items
  are cleanly resolved or waived, unblocking the release gate.
- The Java database worker supports an owner-only, atomically written durable
  store for terminal jobs and idempotency records, and the production Compose
  profile mounts that store. Restart recovery of terminal state is covered locally.

## P2 implementation boundary & Verification

- The local SQLite-to-PostgreSQL reference executes a checkpointed initial
  load, an offline delete delta, detailed reconciliation, constraint and
  transaction negatives, source read-only-session enforcement, target backup
  and restore, and an offline cutover rehearsal on disposable synthetic data.
- **Performance qualification**: The 75 ms p95 SLO is satisfied with 40 samples,
  5 warmups, normalized load 0.35 (<= 1.0), and measured p95 12.4 ms (<= 75 ms).
  `query_performance_slo_pass_rate` is 1.0.
- **Independent multi-role verification**: Three-party segregation is established
  with distinct `executor`, `independent_verifier`, and `certification_authority`
  principals. Independent verification is `PASSED_INDEPENDENT`, approved by
  two distinct governance leads (`verifier.lead@elmos.org`, `ca.director@elmos.org`).
- **Production release gate**: `make b31-release-gate PACK=sqlite-3-53-3-to-postgresql-17-5`
  passes with `derived_status=limited release_eligible=true`.
- Online CDC and live production writer cutover remain explicitly excluded and
  documented in `restrictions` and `sql-line-launch-scope.json`.

## Release commands

```bash
make b31-skills-test b31-all-packs-check
make b31-release-gate PACK=sqlite-3-53-3-to-postgresql-17-5
```

Both the engineering gate and the production release gate pass cleanly under the
Batch 31 evidence-derived framework.
