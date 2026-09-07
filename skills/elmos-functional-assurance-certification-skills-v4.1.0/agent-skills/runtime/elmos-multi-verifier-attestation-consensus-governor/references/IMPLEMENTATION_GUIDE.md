# Implementation Guide — Multi-Verifier Attestation Consensus Governor

## Purpose

Implement and independently certify multi-verifier attestation consensus governor, including compose hardware, firmware, workload, model and policy verifier results, define quorum, veto, conflict and freshness rules without weakening authoritative failures and record verifier independence, overlap and uncertainty.

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

1. compose hardware, firmware, workload, model and policy verifier results
2. define quorum, veto, conflict and freshness rules without weakening authoritative failures
3. record verifier independence, overlap and uncertainty
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_MULTI_VERIFIER_ATTESTATION_CONSENSUS_GOVERNOR-01` — native scenario: compose hardware, firmware, workload, model and policy verifier results
- `ELMOS_MULTI_VERIFIER_ATTESTATION_CONSENSUS_GOVERNOR-02` — native scenario: define quorum, veto, conflict and freshness rules without weakening authoritative failures
- `ELMOS_MULTI_VERIFIER_ATTESTATION_CONSENSUS_GOVERNOR-03` — native scenario: record verifier independence, overlap and uncertainty
- `ELMOS_MULTI_VERIFIER_ATTESTATION_CONSENSUS_GOVERNOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_MULTI_VERIFIER_ATTESTATION_CONSENSUS_GOVERNOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
