# Implementation Guide — Hardware Root of Trust and Measured Boot Verifier

## Purpose

Implement and independently certify hardware root of trust and measured boot verifier, including verify TPM, DICE or platform root measurements from firmware through workload, compare measurements with signed reference values and configuration and bind workload identity, artifact digest and policy decision to boot evidence.

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

1. verify TPM, DICE or platform root measurements from firmware through workload
2. compare measurements with signed reference values and configuration
3. bind workload identity, artifact digest and policy decision to boot evidence
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_HARDWARE_ROOT_OF_TRUST_MEASURED_BOOT_VERIFIER-01` — native scenario: verify TPM, DICE or platform root measurements from firmware through workload
- `ELMOS_HARDWARE_ROOT_OF_TRUST_MEASURED_BOOT_VERIFIER-02` — native scenario: compare measurements with signed reference values and configuration
- `ELMOS_HARDWARE_ROOT_OF_TRUST_MEASURED_BOOT_VERIFIER-03` — native scenario: bind workload identity, artifact digest and policy decision to boot evidence
- `ELMOS_HARDWARE_ROOT_OF_TRUST_MEASURED_BOOT_VERIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_HARDWARE_ROOT_OF_TRUST_MEASURED_BOOT_VERIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
