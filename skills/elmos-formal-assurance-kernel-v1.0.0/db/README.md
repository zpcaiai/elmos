# PostgreSQL 17 migrations

Apply migrations in order with the same migration engine used by Elmos. The scripts assume the application sets `SET LOCAL elmos.tenant_id = '<tenant>'` inside every tenant-scoped transaction.

Production rollout requires:

- backup and restore rehearsal;
- migration on a cloned production-size dataset;
- RLS negative tests;
- lease/fencing race tests;
- immutable artifact tests;
- downgrade/rollback decision recorded in P05 evidence.

This artifact build does not claim the migrations were applied to a live PostgreSQL instance.
