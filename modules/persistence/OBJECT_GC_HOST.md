# Tenant-bound physical object GC

V87 adds a host-internal scheduler path without changing the existing public
`JdbcObjectStorageStore` or V61 SQL signatures. Tenant tables retain FORCE RLS.
The scheduler obtains tenant IDs only from the authoritative organizations
catalog, not from request parameters. PostgreSQL READ COMMITTED is required for
the V86 lock-then-resnapshot root checks.

## Explicit deployment enablement

This path is **disabled by default**. An authorized database operator must grant
`elmos_object_gc_host` to the trusted scheduler login and explicitly enable
`elmos.object-storage.host-gc-enabled=true`. The migration does not grant this
role to `elmos_billing_runtime`, PUBLIC, or any tenant login. This NOLOGIN/NOINHERIT group
has only EXECUTE on three exact host functions, no table privileges and no
BYPASSRLS. Preexisting login/superuser/bypass/inheriting/member-of-other-role
tuples are rejected, not silently reused. The migration owner needs the normal object privileges and CREATEROLE
for initial provisioning; no runtime account needs CREATEROLE. Do not expose
the adapter as a tenant API. Missing privileges fail closed; applying a migration
does not establish production enablement or provider acceptance.

The existing secret-reference resolver and active backend configuration are
reused. The host binds each DELETE to run, tenant, object id, digest, backend id
and canonical storage key. An inactive/mismatched backend or noncanonical key
is unknown, not permission to delete from another backend. Backend configuration
changes and credential provisioning remain governed operator responsibilities.

## Bounded work and locking

One round visits at most 8 tenants and allocates **total** budgets of 256 artifact
marks, 256 AVAILABLE-to-PURGE_PENDING candidates, and 128 DELETE candidates.
The quotas are divided before visiting tenants; they are not multiplied by 8.
These are mutation/candidate bounds, not claims about total physical index/table
tuples examined, legal-hold counting, or provider latency. Tenant and unresolved
item keyset cursors wrap to avoid a permanent failure always taking the first
slot. Metadata lock order is cursor -> run -> object. Acknowledgement takes
run -> exact object. No provider call holds a JDBC connection or transaction;
ambient transactions are rejected rather than suspended around network I/O.

## Unknown and recovery

There is at most one unresolved run per tenant, at most 256 globally, at most
128 exact items per run, and at most 4096 private run records. Unknown retries
update bounded diagnostic fields on the SAME item (counter saturates); they
do not append runs, refresh an expiry, or release a root. Each round may prune
at most 32 **completed** private run records near the history bound. The older
`object_gc_runs` append-only audit is preserved, not silently deleted; its
long-term archival remains an operator retention-policy responsibility.

Expired PREPARED inputs remain retained by V86. A provider timeout, host crash,
interruption, metadata acknowledgement failure or unavailable backend leaves
the durable item unresolved and the object PURGE_PENDING. A later idempotent
DELETE of that same, non-resurrectable tombstone may confirm 2xx/404, then a
short exact-bound transaction advances it to PURGED. This is confirmation of
the current absence, not an invented receipt for the previous attempt. A late
unknown response cannot downgrade a completed item. No timer or caller boolean
can discard unknown work. Exhausted unresolved capacity admits no new runs but
continues cursor rotation and retries existing work. Clearing a genuinely
unreconciled item without provider confirmation requires a separately governed
operator recovery procedure; no such external authority is fabricated here.

The private ledger preserves first/last unknown time and count even after a
subsequent successful retry. Existing audit runs remain RUNNING until every
exact item is confirmed, then finish with the actual confirmed count.

## Local verification boundary

`JdbcTenantObjectRetentionLiveTest` uses only an acknowledged disposable
PostgreSQL database. It exercises ordinary NOBYPASSRLS and privileged function
owners, host-only privileges, context restoration, rollback, fixed round
budgets, cursor rotation, unknown admission/history bounds, exact bindings,
and connection release before a blocked provider callback. Provider callbacks
in this suite are controlled test doubles, not external S3 acceptance or a
performance/certification claim.
