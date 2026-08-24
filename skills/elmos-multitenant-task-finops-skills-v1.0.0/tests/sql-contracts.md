# SQL Contract Checks

The supplied SQL is a reference migration and must be adapted to the target Elmos schema. Repository-specific validation must run it on a disposable PostgreSQL instance.

Minimum checks:

- account slots permit only `slot_no` 1–3;
- `task_id` can occupy only one slot;
- slot claim, renewal, and release use lease generation;
- task submission idempotency is unique by tenant/account/key;
- task events are unique by transition and sequence;
- usage events are unique by idempotency/provider receipt;
- financial ledgers are append-only at the application layer and protected against destructive updates;
- all tenant-scoped tables have `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`;
- application role cannot bypass RLS;
- all rollups are rebuildable from immutable source records.
