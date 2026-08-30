# PostgreSQL migration boundary

`V001__pdhi_control_plane.sql` is an unapplied production-schema contract. It
requires PostgreSQL 16+, a separately provisioned least-privileged NOLOGIN
group role named `pdhi_runtime`, and an independently computed migration byte
digest supplied as transaction setting `elmos.migration_source_sha256`.

The runtime must set `elmos.tenant_id` and `elmos.project_id` with
transaction-local `set_config(..., true)` from the trusted authenticated scope
before every query. Never copy these values from the JSON request body. The
runtime role cannot own tables or hold `BYPASSRLS`; every tenant table uses
both `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`.

The repository has not applied this migration against an external database.
PostgreSQL, failover, backup/restore, pool scope reset, and RLS non-interference
evidence remain `NOT_RUN`; certification remains `NOT_CERTIFIED`.
