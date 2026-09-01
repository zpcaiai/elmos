# What a PostgreSQL deployment of this package actually holds

**Read this before pointing a compliance report, a retention policy or a
restore drill at these tables.**

`postgres-migrate` applies **37 tables**. As of this revision, **22 of them have
no writer anywhere in the package** — including `autonomy_runs`, the root table
that `autonomy_events`, `autonomy_steps`, `autonomy_leases`,
`autonomy_artifacts`, `autonomy_checkpoints`, `autonomy_policy_decisions`,
`autonomy_tool_calls`, `autonomy_evidence` and thirteen more foreign-key to.
They are applied, indexed, backed up and audited, and they stay empty.

Where the data actually goes:

| store | tables | who writes them |
| --- | --- | --- |
| SQLite — `storage.DurableStore` | 27, bare names (`runs`, `events`, `leases`) | every skill handler; `AutonomyRuntime.store` is always this |
| PostgreSQL — `PostgresWaveStore` | 10 (external operations, inbox/outbox, receipts, certification, customer acceptance, secret leases) | the `--postgres-control-service` path |
| PostgreSQL — capability core | 5 (`autonomy_kernel_*`, added by V007) | `elmos_autonomy_kernel.adapters.postgres` |

Measured directly: with every migration applied to a live PostgreSQL 16 server,
a dispatch sequence exercising the lease and cache paths writes three SQLite
tables and **zero** PostgreSQL rows.

A schema that advertises a control plane which is not there is worse than a
missing one, because it gets read, believed, backed up and audited.
`tests/test_persistence_split.py` pins exactly which tables have an
implementation and which do not, and fails if either list moves without the
other.

Closing the split — implementing the 22 against PostgreSQL, or not shipping
them — is an open architecture decision, recorded in
`docs/MERGE_DECISIONS.md`. It is deliberately not made by a cleanup commit.

## Why this note is here and not in `V001__autonomy_run_core.sql`

It was, briefly. The repository gate rejected the package with `released
migration drifted: V001__autonomy_run_core.sql` — a released migration is
digest-pinned and does not change, not even its comments, because a deployment
that already applied it recorded a checksum. The gate was right; the note moved
here.
