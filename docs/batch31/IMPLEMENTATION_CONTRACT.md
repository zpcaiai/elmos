
# Batch 31 Implementation Contract

## Purpose

Batch 31 turns database, SQL, routine, ETL, warehouse, and data-migration capabilities into directional, version-specific, executable database packs. A pack is not a marketing matrix: it is a reproducible implementation with real engine evidence and explicit limitations.

## Required implementation shape

Every production-shaped pack must contain:

1. exact source and target engine/version/edition/provider tuples;
2. accountable, maintenance, and data owners;
3. static and runtime workload fingerprinting;
4. typed canonical database IR with source maps and provider extensions;
5. exact target profile and driver/toolchain locks;
6. deterministic transformations for the certified scope;
7. disposable source and target environments or approved licensed evidence;
8. development, negative, holdout, and representative workload corpora;
9. schema, data, query, routine, transaction, pipeline, performance, security, and rollback evidence as applicable;
10. a conservative certification status produced by the gate.

## Required execution discipline

- Inspect repository-native commands and existing adapters before adding new tooling.
- Use read-only discovery against customer systems unless a separate production workflow explicitly authorizes writes.
- Prefer snapshots, clones, disposable schemas, masked data, or synthetic fixtures.
- Parse DDL, SQL, routines, and pipelines into typed IR; never use regex as the core migration architecture.
- Keep source truth, target implementation, and comparison evidence separate.
- Run real source and target engines and clients.
- Fix systemic failures at discovery, IR, capability, transformation, or generator layers.
- Preserve customer-owned SQL, routines, data contracts, and target extensions through explicit ownership metadata.

## Required evidence identity

Every result must reference:

- source snapshot/catalog/data/workload digest;
- target snapshot and release digest;
- engine, edition, driver, compatibility, charset, collation, time-zone, and extension tuple;
- canonical IR schema and artifact digest;
- transformation/recipe and compatibility-runtime digests;
- runner/toolchain/container digest;
- query-plan/workload and data-fixture digests;
- acceptance profile, approvals, and gate result.

## Certification boundary

Certification is directional and scoped. For example, Oracle 19c Enterprise to PostgreSQL 16 with a declared subset does not certify PostgreSQL to Oracle, another Oracle edition, a cloud compatibility layer, or unsupported routines and extensions.
