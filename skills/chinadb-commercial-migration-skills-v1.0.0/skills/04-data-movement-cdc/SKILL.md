# Commercial Data Movement & CDC

- **Skill ID:** `04-data-movement-cdc`
- **Version:** `1.0.0`
- **Category:** core/data
- **Implementation status:** specification only until repository evidence proves otherwise

## Objective

Move initial and incremental data safely at enterprise scale with chunking, parallelism, resume/retry, CDC gap protection, LOB handling, type fidelity, reconciliation and rollback-aware cutover.

## Inputs

- Source/target connection profiles
- Table dependency/size profile
- Type mappings
- CDC mechanism selection
- RPO/RTO/window constraints

## Required outputs

- Full-load plan
- CDC stream/checkpoint config
- Per-table progress journal
- Reconciliation results
- Sequence/identity alignment report
- Cutover catch-up status

## Implementation modules / repository contract

- data/plan.py
- data/chunker.py
- data/load.py
- data/cdc.py
- data/checkpoints.py
- data/type_codec.py
- data/lob.py
- data/reconcile.py
- data/sequence_align.py

## Interfaces and contracts

- Movement engine exposes snapshot position and exact cutover catch-up state
- Data codecs are route/version aware

## Workflow

1. Choose vendor-native movement integration when available and contractually allowed; otherwise use generic connectors.
2. Order/defer constraints and dependencies safely.
3. Chunk by stable keys; support large tables, partitions and LOB streaming.
4. Persist source log position and target apply checkpoint atomically.
5. Handle DDL during migration through an explicit policy.
6. Reconcile row counts plus keyed/partitioned checksums and selected field-level samples.
7. Align sequences/identities and prove no key collision before cutover.
8. Support reverse/rollback stream when route policy requires it.

## Mandatory tests

- Network interruption and resume
- Duplicate/replayed CDC events
- Out-of-order events
- Delete/update during full load
- LOB > memory chunk
- Timezone/collation/encoding edge values
- No-primary-key tables
- Partition key updates
- Schema change during CDC
- Sequence collision at cutover

## Required evidence

- Per-table copy metrics
- CDC source/target positions
- Gap detector results
- Checksum evidence
- Rejected-row quarantine
- Sequence alignment evidence

## Fail-closed / escalation rules

- No cutover if CDC gap is unknown.
- No silent truncation/rounding/character replacement.
- Rejected rows must block certification unless explicitly waived.

## Definition of Done

- Actual implementation exists in the product repository; no stub-only completion.
- Required unit/integration fixtures execute in CI and include negative cases.
- Evidence artifacts conform to schemas/evidence.schema.json and reference real logs/results.
- No silent semantic fallback: unsupported or ambiguous cases are explicit.
- Documentation, config schema and route/version compatibility declarations are updated.
- The skill's release gate is reproducible from a clean checkout.
