# Gap inventory

Repository-owned local query preparation is complete for the declared bounded
scope. It does not close the following external gates:

- Provision licensed, disposable PostgreSQL 17.5 and DM8 8.1.3.140 Enterprise
  engines with the exact drivers, compatibility mode, charset, collation, and
  timezone recorded by the pack. Record immutable source/target image and
  driver digests, exact patch output, and an Enterprise-license verification
  receipt; every one is currently `NOT_RUN` / unprovisioned.
- Execute source and target schema, query, type-boundary, transaction,
  constraint, security, and failure-path workloads.
- Use independent holdout and representative corpora; the reserved directories
  intentionally contain no developer-authored passing cases.
- Reconcile every migrated row and column, prove exact money handling, capture
  CDC positions, and run authorized cutover and rollback drills.
- Meet the independent DM8 query-performance SLO and preserve raw plans and
  latency distributions on an attested, dedicated, exclusive Runner using five
  warmups and 40 samples per query on both engines with p95 at most 75 ms.
- Engage an independent verifier whose person and organization are distinct
  from both implementer and executor, then submit the immutable evidence bundle
  to the Batch 31 gate for the sole certification decision.

Until all items are evidenced, external execution is `NOT_RUN` and production
certification is `NOT_CERTIFIED`.
