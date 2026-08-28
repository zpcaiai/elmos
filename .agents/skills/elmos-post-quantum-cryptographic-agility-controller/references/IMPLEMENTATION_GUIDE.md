# Implementation Guide — Post-Quantum Cryptographic Agility Controller

## Purpose

Implement and independently certify post-quantum cryptographic agility controller, including inventory vulnerable public-key uses and long-lived evidence signatures, plan ML-KEM, ML-DSA, SLH-DSA and future algorithm transition with crypto-agility and test hybrid negotiation, downgrade resistance, archival verification and rollback.

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

1. inventory vulnerable public-key uses and long-lived evidence signatures
2. plan ML-KEM, ML-DSA, SLH-DSA and future algorithm transition with crypto-agility
3. test hybrid negotiation, downgrade resistance, archival verification and rollback
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_POST_QUANTUM_CRYPTOGRAPHIC_AGILITY_CONTROLLER-01` — native scenario: inventory vulnerable public-key uses and long-lived evidence signatures
- `ELMOS_POST_QUANTUM_CRYPTOGRAPHIC_AGILITY_CONTROLLER-02` — native scenario: plan ML-KEM, ML-DSA, SLH-DSA and future algorithm transition with crypto-agility
- `ELMOS_POST_QUANTUM_CRYPTOGRAPHIC_AGILITY_CONTROLLER-03` — native scenario: test hybrid negotiation, downgrade resistance, archival verification and rollback
- `ELMOS_POST_QUANTUM_CRYPTOGRAPHIC_AGILITY_CONTROLLER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_POST_QUANTUM_CRYPTOGRAPHIC_AGILITY_CONTROLLER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
