# Implementation Guide — AI Content Provenance and Labeling Controller

## Purpose

Generate provenance metadata, disclosures, watermarks or content credentials and verify that transformations preserve required labels.

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

1. Content origin and transformation chain
2. Region/channel-specific disclosure policy
3. Metadata/visible label/watermark selection
4. Derivative preservation checks
5. Tamper and removal detection

## Native acceptance corpus

- `ELMOS_AI_CONTENT_PROVENANCE_LABELING_CONTROLLER-01` — text disclosure
- `ELMOS_AI_CONTENT_PROVENANCE_LABELING_CONTROLLER-02` — image credential
- `ELMOS_AI_CONTENT_PROVENANCE_LABELING_CONTROLLER-03` — derivative preservation
- `ELMOS_AI_CONTENT_PROVENANCE_LABELING_CONTROLLER-04` — channel export
- `ELMOS_AI_CONTENT_PROVENANCE_LABELING_CONTROLLER-05` — tamper detection
- `ELMOS_AI_CONTENT_PROVENANCE_LABELING_CONTROLLER-06` — required label missing

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
