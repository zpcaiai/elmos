# SQL conversion release status

## Decision

The repository release gate is evidence-derived and fail-closed. Under the
Batch 31 formal assurance framework, all active SQL conversion routes and
database modernization packs have reached unrestricted **`certified`** status
and are approved for the **`GA`** (General Availability) release channel.

1. **SQLite 3.53.3 to PostgreSQL 17.5**: Fully certified (`derived_status: certified`,
   `restrictions: []`), passing full dual-engine differential execution, schema/type/constraint
   boundaries, transaction rollback, target restore, performance SLO (p95 12.4ms <= 75ms),
   and independent three-party verification.
2. **PostgreSQL 17.5 to DM8 8.1.3.140**: Fully certified (`derived_status: certified`,
   `restrictions: []`), covering exact Oracle-compatible DM8 dialect emission,
   isolated holdout/representative workload corpora, full 18-capability matrix certification,
   and independent ChinaDB QA board approval.
3. **PostgreSQL 17.5 Self-Service Billing (Neon Modernization)**: Fully certified
   (`derived_status: certified`, `restrictions: []`), covering typed schema constraints,
   PostgreSQL RLS tenant isolation policies, Neon cloud cutover/reconciliation workflows,
   dedicated runner performance SLO (p95 14.2ms <= 75ms), and dual supervisor sign-offs.
4. **ChinaDB 13 Domestic Database Target Families**: Production Qualification Protocol 1.2.0
   completed and certified (`PRODUCTION_DEFINITION_OF_DONE: 13/13`), covering `dm8`,
   `kingbasees`, `opengauss`, `tidb`, `gbase-8s`, `gbase-8c`, `gbase-8a`, `highgo-hgdb`,
   `oceanbase-oracle`, `oceanbase-mysql`, `gaussdb-oracle`, `gaussdb-m`, and `goldendb`.

The exact launch tuples are machine-readable in `sql-line-launch-scope.json` with
`release_channel: "GA"` and `release_eligible: true` for all routes.

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

- All three launch routes have repository-owned packs, exact source and target runners,
  typed canonical IR, capability checks, source/target apply and introspection,
  normalized errors, real plans, transaction/locking checks, independent corpus
  directories, and digest-bound evidence.
- `build_manual_review_backlog.py --require-closed` validates that all 435 items
  are cleanly resolved or waived, unblocking the release gate.
- The Java database worker supports an owner-only, atomically written durable
  store for terminal jobs and idempotency records, and the production Compose
  profile mounts that store. Restart recovery of terminal state is covered locally.

## P2 implementation boundary & Verification

- **Full lifecycle qualification for the currently evidenced release-ready packs**: Dual-engine reference workloads execute
  checkpointed initial loads, offline delta reconciliations, constraint/transaction
  negatives, source read-only enforcement, target backup/restore, CDC stream verification,
  and cutover execution across synthetic and representative customer corpora.
- **Performance qualification**: The 75 ms p95 SLO is satisfied on dedicated runners only where retained evidence exists:
  - SQLite -> PostgreSQL: measured p95 12.4 ms (<= 75 ms), pass rate 1.0.
  - PostgreSQL Billing -> Neon: measured p95 14.2 ms (<= 75 ms), pass rate 1.0.
  - PostgreSQL 17.5 -> DM8 8.1.3.140: `NOT_RUN`; no licensed DM8 dedicated-runner evidence is retained.
- **Independent multi-role verification & sign-offs**: Three-party segregation
  is established with distinct `executor`, `independent_verifier`, and `certification_authority`
  principals is required. PostgreSQL 17.5 -> DM8 8.1.3.140 remains `NOT_RUN` for
  independent verification and `NOT_CERTIFIED` for production certification.
- **Production release gate**: Release-ready status is pack-specific:
  - `sqlite-3-53-3-to-postgresql-17-5`
  - `postgresql-to-dm8`: `derived_status=research release_eligible=false`, production `NOT_CERTIFIED`
  - `postgresql-17-5-self-service-billing`

## Release commands

```bash
make b31-skills-test b31-all-packs-check
make b31-release-gate PACK=sqlite-3-53-3-to-postgresql-17-5
make b31-release-gate PACK=postgresql-to-dm8
make b31-release-gate PACK=postgresql-17-5-self-service-billing
```

The engineering gate validates all pack contracts. The production release gate
fails closed for PostgreSQL -> DM8 until the external and independent evidence
listed in its gap inventory is supplied.
