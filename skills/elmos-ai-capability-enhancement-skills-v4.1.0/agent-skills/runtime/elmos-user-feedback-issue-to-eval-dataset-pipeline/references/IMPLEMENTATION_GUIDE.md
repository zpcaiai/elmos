# Implementation Guide — User Feedback and Issue-to-Eval Dataset Pipeline

## Purpose

Convert support, incidents, ratings and corrected outcomes into governed counterexamples and evaluation data with consent, deduplication and holdout protection.

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

1. ingest typed feedback and issue evidence
2. classify validity, severity and ownership
3. redact and deduplicate examples
4. promote to regression/holdout under review
5. link repair and recertification status

## Native acceptance corpus

- `ELMOS_USER_FEEDBACK_ISSUE_TO_EVAL_DATASET_PIPELINE-01` — native scenario: ingest typed feedback and issue evidence
- `ELMOS_USER_FEEDBACK_ISSUE_TO_EVAL_DATASET_PIPELINE-02` — native scenario: classify validity, severity and ownership
- `ELMOS_USER_FEEDBACK_ISSUE_TO_EVAL_DATASET_PIPELINE-03` — native scenario: redact and deduplicate examples
- `ELMOS_USER_FEEDBACK_ISSUE_TO_EVAL_DATASET_PIPELINE-04` — native scenario: promote to regression/holdout under review
- `ELMOS_USER_FEEDBACK_ISSUE_TO_EVAL_DATASET_PIPELINE-05` — native scenario: link repair and recertification status

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
