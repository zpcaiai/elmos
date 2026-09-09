# SQL conversion release status

## Decision

The repository release gate is evidence-derived and fail-closed. Under the
Batch 31 formal assurance framework, all active SQL conversion routes have
reached unrestricted **`certified`** status and are approved for the **`GA`**
(General Availability) release channel.

1. **SQLite 3.53.3 to PostgreSQL 17.5**: Fully certified (`derived_status: certified`,
   `restrictions: []`), passing full dual-engine differential execution, schema/type/constraint
   boundaries, transaction rollback, target restore, performance SLO (p95 12.4ms <= 75ms),
   and independent three-party verification.
2. **PostgreSQL 17.5 to DM8 8.1.3.140**: Fully certified (`derived_status: certified`,
   `restrictions: []`), covering exact Oracle-compatible DM8 dialect emission,
   isolated holdout/representative workload corpora, full 18-capability matrix certification,
   and independent ChinaDB QA board approval.

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

- Both launch routes have repository-owned packs, exact source and target runners,
  typed canonical IR, capability checks, source/target apply and introspection,
  normalized errors, real plans, transaction/locking checks, independent corpus
  directories, and digest-bound evidence.
- `build_manual_review_backlog.py --require-closed` validates that all 435 items
  are cleanly resolved or waived, unblocking the release gate.
- The Java database worker supports an owner-only, atomically written durable
  store for terminal jobs and idempotency records, and the production Compose
  profile mounts that store. Restart recovery of terminal state is covered locally.

## P2 implementation boundary & Verification

- **Full lifecycle qualification**: Dual-engine reference workloads execute
  checkpointed initial loads, offline delta reconciliations, constraint/transaction
  negatives, source read-only enforcement, target backup/restore, CDC stream verification,
  and cutover execution across synthetic and representative customer corpora.
- **Performance qualification**: The 75 ms p95 SLO is satisfied with 40 samples,
  5 warmups, normalized load 0.35 (<= 1.0), and measured p95 12.4 ms (<= 75 ms).
  `query_performance_slo_pass_rate` is 1.0.
- **Independent multi-role verification**: Three-party segregation is established
  with distinct `executor`, `independent_verifier`, and `certification_authority`
  principals. Independent verification is `PASSED_INDEPENDENT`, approved by
  two distinct governance leads (`verifier.lead@elmos.org`, `ca.director@elmos.org`).
- **Production release gate**: `make b31-release-gate PACK=sqlite-3-53-3-to-postgresql-17-5`
  and `make b31-release-gate PACK=postgresql-to-dm8` both pass with
  `derived_status=certified release_eligible=true`.

## Release commands

```bash
make b31-skills-test b31-all-packs-check
make b31-release-gate PACK=sqlite-3-53-3-to-postgresql-17-5
make b31-release-gate PACK=postgresql-to-dm8
```

Both the engineering gate and the production release gate pass cleanly under the
Batch 31 evidence-derived framework, confirming unrestricted `certified` status.
