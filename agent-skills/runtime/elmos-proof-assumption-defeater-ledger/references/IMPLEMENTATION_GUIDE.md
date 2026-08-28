# Implementation Guide — Proof Assumption and Defeater Ledger

## Purpose

Implement and independently certify proof assumption and defeater ledger, including enumerate explicit assumptions, environmental contracts and argument defeaters, link evidence that supports or challenges each assumption and invalidate dependent claims when assumption freshness or truth changes.

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

1. enumerate explicit assumptions, environmental contracts and argument defeaters
2. link evidence that supports or challenges each assumption
3. invalidate dependent claims when assumption freshness or truth changes
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_PROOF_ASSUMPTION_DEFEATER_LEDGER-01` — native scenario: enumerate explicit assumptions, environmental contracts and argument defeaters
- `ELMOS_PROOF_ASSUMPTION_DEFEATER_LEDGER-02` — native scenario: link evidence that supports or challenges each assumption
- `ELMOS_PROOF_ASSUMPTION_DEFEATER_LEDGER-03` — native scenario: invalidate dependent claims when assumption freshness or truth changes
- `ELMOS_PROOF_ASSUMPTION_DEFEATER_LEDGER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_PROOF_ASSUMPTION_DEFEATER_LEDGER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
