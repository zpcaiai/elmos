# Implementation Guide — Model Provider Procurement and Contract Evaluator

## Purpose

Evaluate provider SLA, data use, retention, residency, indemnity, deprecation, quota, pricing and exit terms against technical requirements.

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

1. compile technical and contractual requirement matrix
2. map provider terms to controls and unresolved legal review
3. model deprecation, outage and exit scenarios
4. compare total cost and data exposure
5. generate procurement evidence without legal conclusion

## Native acceptance corpus

- `ELMOS_MODEL_PROVIDER_PROCUREMENT_CONTRACT_EVALUATOR-01` — native scenario: compile technical and contractual requirement matrix
- `ELMOS_MODEL_PROVIDER_PROCUREMENT_CONTRACT_EVALUATOR-02` — native scenario: map provider terms to controls and unresolved legal review
- `ELMOS_MODEL_PROVIDER_PROCUREMENT_CONTRACT_EVALUATOR-03` — native scenario: model deprecation, outage and exit scenarios
- `ELMOS_MODEL_PROVIDER_PROCUREMENT_CONTRACT_EVALUATOR-04` — native scenario: compare total cost and data exposure
- `ELMOS_MODEL_PROVIDER_PROCUREMENT_CONTRACT_EVALUATOR-05` — native scenario: generate procurement evidence without legal conclusion

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
