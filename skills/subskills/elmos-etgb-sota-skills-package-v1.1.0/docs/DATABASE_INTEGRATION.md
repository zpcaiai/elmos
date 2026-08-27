# Elmos database integration

`integrations/postgres/001_etgb_schema.sql` provides benchmark definitions, frozen candidates/plans, Environment authority, durable run/shard/case state, transitions, checkpoints, Oracle results, evidence, budgets, gates, failures, regressions, idempotency and outbox.

`002_etgb_rls.sql` enables forced tenant RLS. Application transactions must set `SET LOCAL app.tenant_id`. The runtime role must not have `BYPASSRLS`.

## CAS transition example

```sql
UPDATE etgb.benchmark_run
SET status = :target, revision = revision + 1, updated_at = now()
WHERE run_id = :run_id
  AND tenant_id = etgb.current_tenant_id()
  AND status = :expected
  AND revision = :expected_revision
  AND fencing_token = :fencing_token;
```

Require exactly one updated row, then insert `run_transition` and outbox event in the same transaction.

## Account concurrency

Admission queries active runs by account and enforces the default maximum of three. Use a transaction/advisory lock or serialized quota row so concurrent admissions cannot race.
