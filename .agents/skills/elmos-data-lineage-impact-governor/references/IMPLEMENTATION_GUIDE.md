# Implementation Guide — Data Lineage and Impact Governor

## Purpose

Collect and verify dataset, column, model, prompt, retrieval and generated-artifact lineage so changes invalidate every affected route and certificate.

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

1. ingest OpenLineage-compatible run and dataset events
2. derive column and semantic lineage
3. link data to models, prompts and outputs
4. compute change impact and evidence invalidation
5. export auditable lineage with confidence

## Native acceptance corpus

- `ELMOS_DATA_LINEAGE_IMPACT_GOVERNOR-01` — native scenario: ingest OpenLineage-compatible run and dataset events
- `ELMOS_DATA_LINEAGE_IMPACT_GOVERNOR-02` — native scenario: derive column and semantic lineage
- `ELMOS_DATA_LINEAGE_IMPACT_GOVERNOR-03` — native scenario: link data to models, prompts and outputs
- `ELMOS_DATA_LINEAGE_IMPACT_GOVERNOR-04` — native scenario: compute change impact and evidence invalidation
- `ELMOS_DATA_LINEAGE_IMPACT_GOVERNOR-05` — native scenario: export auditable lineage with confidence

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
