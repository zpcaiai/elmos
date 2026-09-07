# PostgreSQL integration

Apply `001_etgb_schema.sql`, then `002_etgb_rls.sql`. Every application transaction must set a local tenant context before accessing ETGB tables:

```sql
BEGIN;
SET LOCAL app.tenant_id = '00000000-0000-0000-0000-000000000001';
-- ETGB operations
COMMIT;
```

The application role must not bypass RLS. Administrative and migration roles should be separate, audited roles. Run-state updates must use `WHERE run_id=? AND revision=? AND fencing_token=?`, increment `revision`, and insert `run_transition` in the same transaction. Billing writes and outbox events must share one transaction.
