
# Batch 31 Database Pack Quality Gates

## Gate D31-A — Exact route, ownership, and safety

- pack manifest validates;
- exact source/target engines, versions, editions, dialects, drivers, charsets, collations, time zones, extensions, and operating modes are recorded;
- accountable, maintenance, and data owners exist;
- source collection and target execution use approved data-safety profiles;
- no floating versions, mutable images, or production-write assumptions.

## Gate D31-B — Source estate and workload fingerprint

- catalog, DDL, security, configuration, dependencies, sizes, and jobs are discovered;
- runtime SQL, plans, waits, locks, schedules, and data distributions are captured for certified scope;
- declared, active, conditional, generated, test-only, deprecated, and unknown facts are distinguished;
- critical fingerprint coverage meets threshold;
- sensitive values and credentials are minimized.

## Gate D31-C — Canonical database IR

- schema, types, constraints, indexes, partitions, generators, views, routines, triggers, queries, transactions, and pipelines are represented as required;
- stable identities, source trace, dependencies, semantic properties, and provider extensions exist;
- critical IR coverage meets threshold;
- no regex-only transformation or silent object loss.

## Gate D31-D — Schema and procedural correctness

- target provisioning succeeds on the exact engine;
- type boundary, precision, null, collation, and time-zone suites pass;
- constraints, indexes, partitions, generators, views, routines, and triggers pass applicable positive/negative tests;
- destructive or lossy changes have approved migration plans;
- critical precision and collation regressions are zero.

## Gate D31-E — Query, transaction, and workload correctness

- P0 query result and error contracts pass;
- transaction, isolation, locking, retry, and rollback contracts pass;
- generated queries are parameterized and no unsafe client-side evaluation is used;
- representative query plans meet SLO or approved capacity plan;
- critical transaction and security regressions are zero.

## Gate D31-F — Data and pipeline migration

- historical backfill is checkpointed and reconciled;
- CDC/delta/delete propagation is durable where required;
- data-quality findings are source-traced and unresolved critical differences are zero;
- pipelines preserve state, watermark, idempotency, retry, and SLA contracts;
- rollback/forward-recovery and restore are rehearsed.

## Gate D31-G — Independent evidence and lifecycle

- holdout and representative workload corpora are physically separate and non-empty;
- holdout cases were not used to author transformations;
- evidence refs exist and digests are verifiable;
- provider/route lifecycle, compatibility components, maintenance, costs, and recertification triggers exist;
- customer-owned data and target code are protected.

## Certification outcomes

- `certified`: all required gates pass for the exact tuple and scope;
- `limited`: useful, safe subset with explicit conditions and blockers;
- `experimental`: implementation exists but independent or operational evidence is insufficient;
- `blocked`: a critical correctness, precision, security, transaction, data, performance, rollback, or maintenance requirement fails.
