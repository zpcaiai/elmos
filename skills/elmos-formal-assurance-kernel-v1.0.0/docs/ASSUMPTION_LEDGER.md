# Assumption Ledger Operating Standard

## Required fields

Each assumption records an ID, natural-language statement, optional formal expression, source, owner, risk, validity period, monitor, evidence, hash and affected proof set.

## Examples

- PostgreSQL enforces the declared PK/FK/CHECK constraints.
- Reflection targets are limited to the enumerated classpath manifest.
- The system clock is monotonic within the stated tolerance.
- The target database uses the specified collation and time-zone database.
- An external payment API honors its idempotency contract.
- Native code modifies only the declared memory region.

## Lifecycle

```text
PROPOSED → ACTIVE → VIOLATED / EXPIRED / REVOKED
```

A proof may cite only ACTIVE assumptions. High and critical assumptions require an owner and a monitor or explicit explanation why monitoring is impossible. Expiry or violation immediately marks dependent evidence stale.

## Prohibited patterns

- embedding assumptions only in prose;
- using “normal runtime behavior” without a measurable contract;
- inheriting compiler or database semantics from an unpinned environment;
- treating test fixtures as universal input constraints;
- silently assuming no concurrency, no overflow or no NULL values;
- deleting an assumption after proof creation.

## Review cadence

Critical assumptions are reviewed for every release and drift event. High-risk assumptions are reviewed at least quarterly. The release gate uses current status, not the status at proof creation time.
