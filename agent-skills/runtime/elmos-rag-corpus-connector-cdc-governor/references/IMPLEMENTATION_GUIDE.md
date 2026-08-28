# Implementation Guide — RAG Corpus Connector and CDC Governor

## Purpose

Generate reliable corpus connectors with snapshots, change data capture, resumable sync, deduplication, ordering, tombstones and reindex governance.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. Snapshot plus CDC handoff
2. Idempotent event ordering and deduplication
3. Connector checkpoint/replay
4. Tombstone and reindex lifecycle
5. Source-to-index lineage

## Native acceptance corpus

- `ELMOS_RAG_CORPUS_CONNECTOR_CDC_GOVERNOR-01` — initial snapshot
- `ELMOS_RAG_CORPUS_CONNECTOR_CDC_GOVERNOR-02` — concurrent CDC handoff
- `ELMOS_RAG_CORPUS_CONNECTOR_CDC_GOVERNOR-03` — duplicate/out-of-order event
- `ELMOS_RAG_CORPUS_CONNECTOR_CDC_GOVERNOR-04` — crash resume
- `ELMOS_RAG_CORPUS_CONNECTOR_CDC_GOVERNOR-05` — delete propagation
- `ELMOS_RAG_CORPUS_CONNECTOR_CDC_GOVERNOR-06` — full reindex reconciliation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
