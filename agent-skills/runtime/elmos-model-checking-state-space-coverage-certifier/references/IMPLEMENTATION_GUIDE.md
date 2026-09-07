# Implementation Guide — Model Checking State-Space Coverage Certifier

## Purpose

Implement and independently certify model checking state-space coverage certifier, including declare state variables, bounds, fairness, symmetry and reduction assumptions, report explored state space, counterexamples and unsearched regions and separate bounded model checking from unbounded proof.

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

1. declare state variables, bounds, fairness, symmetry and reduction assumptions
2. report explored state space, counterexamples and unsearched regions
3. separate bounded model checking from unbounded proof
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_MODEL_CHECKING_STATE_SPACE_COVERAGE_CERTIFIER-01` — native scenario: declare state variables, bounds, fairness, symmetry and reduction assumptions
- `ELMOS_MODEL_CHECKING_STATE_SPACE_COVERAGE_CERTIFIER-02` — native scenario: report explored state space, counterexamples and unsearched regions
- `ELMOS_MODEL_CHECKING_STATE_SPACE_COVERAGE_CERTIFIER-03` — native scenario: separate bounded model checking from unbounded proof
- `ELMOS_MODEL_CHECKING_STATE_SPACE_COVERAGE_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_MODEL_CHECKING_STATE_SPACE_COVERAGE_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
