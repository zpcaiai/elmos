# Implementation Guide — Data Quality Contract and Anomaly Verifier

## Purpose

Define and enforce completeness, freshness, validity, uniqueness, distribution, drift and business-invariant contracts for operational, RAG and evaluation data.

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

1. compile declarative quality contracts
2. run batch and streaming checks
3. detect distribution and semantic drift
4. attribute anomalies to upstream lineage
5. block affected model, retrieval and migration claims

## Native acceptance corpus

- `ELMOS_DATA_QUALITY_CONTRACT_ANOMALY_VERIFIER-01` — native scenario: compile declarative quality contracts
- `ELMOS_DATA_QUALITY_CONTRACT_ANOMALY_VERIFIER-02` — native scenario: run batch and streaming checks
- `ELMOS_DATA_QUALITY_CONTRACT_ANOMALY_VERIFIER-03` — native scenario: detect distribution and semantic drift
- `ELMOS_DATA_QUALITY_CONTRACT_ANOMALY_VERIFIER-04` — native scenario: attribute anomalies to upstream lineage
- `ELMOS_DATA_QUALITY_CONTRACT_ANOMALY_VERIFIER-05` — native scenario: block affected model, retrieval and migration claims

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
