# CAS publication without long database transactions

V85 and `JdbcCasCatalog` retain the existing four durable-publication method signatures.
Their JDBC implementation now uses three phases:

1. Short transaction: authenticate tenant context, lock tenant → resource (if supplied) →
   sorted object identities, validate ACTIVE epochs and deletion tombstones, then commit a
   unique publication's durable object pins. Close/return the database connection.
2. Execute the existing synchronous `DurableObjectEnsurer` outside any catalogue connection
   or database lock. Hashing, private staging, encryption, durable writes and verified reads
   therefore do not serialize unrelated tenant objects through a held JDBC transaction.
3. Short transaction: repeat lifecycle/object lock order, revalidate exact tenant/resource
   epochs and unexpired ACTIVE pins, clear only repairable deletion tombstones, and atomically
   publish metadata/bindings/complete root generation plus RELEASED pin state.

The PostgreSQL connection wrapper still rejects ambient transactions and retains its original
rollback/abort/pool-reset contract. The controlled-schedule test checks connection count zero
while a callback is paused, then publishes another object of the same tenant before unblocking
the first callback. This is a concurrency property, not a throughput benchmark.

## GC, retirement and recovery

GC takes the same per-object lock before consulting pins. Both `deleteIfUnreferenced` and a
database trigger refuse deletion when **any** ACTIVE or OUTCOME_UNKNOWN pin exists, including
an expired pin. Resource/tenant retirement need not wait for physical I/O; late publication
fails the epoch/ACTIVE-state check. Bytes left behind are not authorization or live roots.

Publication leases default to 30 minutes, with a host-owned 1-second–1-hour constructor budget.
Expiry revokes permission to publish, never proves that a delayed writer has stopped.
`reconcilePublicationPins(tenant)` classifies expired ACTIVE rows as OUTCOME_UNKNOWN. It does
not release them. Successful synchronous callbacks establish completion. Failed generic or
provider-backed callbacks do not: they immediately retain an OUTCOME_UNKNOWN fence, since a
network timeout cannot prove remote termination. The exact repository-owned LocalDisk and
encrypted-local stores return a typed `LocalCasPublication` through `publicationEnsurer`, which
executes only their fixed staged-object write/verify sequence and records local I/O termination.
Only that internal type can establish quiescence after a failure; there is no user boolean.
`CasBackedArtifactStore` uses this typed path. A successful callback followed by epoch or metadata
rejection can safely release its pin, because the physical I/O already completed.

If a process dies or a cleanup transaction cannot be confirmed, the pin remains fail-closed.
There is deliberately no user boolean, generic force-release method, or TTL-based deletion
shortcut. Cross-process recovery requires host-owned proof of writer fencing and reconciled
provider effects; this repository currently lacks that trusted recovery adapter. Such entries
remain OUTCOME_UNKNOWN and must be escalated, not silently expired away. A test JVM exits
abruptly inside the callback to exercise this persisted fence.

There are at most 128 unresolved object pins per tenant, and 128 objects per publication.
Admission fails before I/O when that budget is exhausted; unknown pins count against it.
Released history is a bounded rolling diagnostic log: up to 24 hours or approximately 4096
rows per tenant (plus the bounded in-flight/next-maintenance batch), whichever bound is reached
first. Each maintenance pass prunes at most 256 released rows. UNKNOWN rows are never pruned.
This table is not a substitute for an independently retained compliance audit trail.

## Migration, permissions and rollback

Apply V85 before running the new JDBC writer. Its pin table has forced RLS, exact tenant
policy, and no PUBLIC table privileges. The host's existing trusted CAS runtime role needs
SELECT/INSERT/UPDATE/DELETE on this one additional table; do not grant access to other tenants,
schema ownership, bypass-RLS, or superuser rights. The tests use a separate NOSUPERUSER,
NOBYPASSRLS fixture role in an explicitly confirmed disposable database.

Do not drop V85 or run a v2-only catalogue/GC writer while unresolved pins exist. Recovery
must retain the pin-aware deletion guard; disabling that trigger is not a rollback strategy.
No migration, provider call or production permission change is performed by this document.

Local controlled schedules and the real PostgreSQL 17.5 test tuple are engineering evidence
only. Crash fixture/process tests, byte/digest identity, RLS and concurrency are not independent
certification, provider reconciliation evidence, or a production SLO claim.
