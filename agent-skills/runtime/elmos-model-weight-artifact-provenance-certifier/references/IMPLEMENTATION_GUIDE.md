# Implementation Guide — Model Weight and Artifact Provenance Certifier

## Purpose

Certify model weights, tokenizer, adapters, quantization, conversion and serving artifacts from source through registry, build, signature and deployment.

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

1. inventory weight, tokenizer, adapter and config digests
2. trace conversion, merge, quantization and packaging lineage
3. verify signatures, licenses and allowed use
4. reproduce selected artifact transformations
5. bind serving deployment to certified artifact graph

## Native acceptance corpus

- `ELMOS_MODEL_WEIGHT_ARTIFACT_PROVENANCE_CERTIFIER-01` — native scenario: inventory weight, tokenizer, adapter and config digests
- `ELMOS_MODEL_WEIGHT_ARTIFACT_PROVENANCE_CERTIFIER-02` — native scenario: trace conversion, merge, quantization and packaging lineage
- `ELMOS_MODEL_WEIGHT_ARTIFACT_PROVENANCE_CERTIFIER-03` — native scenario: verify signatures, licenses and allowed use
- `ELMOS_MODEL_WEIGHT_ARTIFACT_PROVENANCE_CERTIFIER-04` — native scenario: reproduce selected artifact transformations
- `ELMOS_MODEL_WEIGHT_ARTIFACT_PROVENANCE_CERTIFIER-05` — native scenario: bind serving deployment to certified artifact graph

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
