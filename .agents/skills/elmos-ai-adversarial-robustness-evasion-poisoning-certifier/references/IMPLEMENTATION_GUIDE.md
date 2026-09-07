# Implementation Guide — Adversarial Robustness, Evasion and Poisoning Certifier

## Purpose

Implement and independently certify adversarial robustness, evasion and poisoning certifier, including map attacker goals, knowledge, capability and lifecycle stage to test campaigns, evaluate evasion, poisoning, privacy and generative misuse defenses and measure adaptive attack success and residual risk rather than static checklist compliance.

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

1. map attacker goals, knowledge, capability and lifecycle stage to test campaigns
2. evaluate evasion, poisoning, privacy and generative misuse defenses
3. measure adaptive attack success and residual risk rather than static checklist compliance
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_ADVERSARIAL_ROBUSTNESS_EVASION_POISONING_CERTIFIER-01` — native scenario: map attacker goals, knowledge, capability and lifecycle stage to test campaigns
- `ELMOS_AI_ADVERSARIAL_ROBUSTNESS_EVASION_POISONING_CERTIFIER-02` — native scenario: evaluate evasion, poisoning, privacy and generative misuse defenses
- `ELMOS_AI_ADVERSARIAL_ROBUSTNESS_EVASION_POISONING_CERTIFIER-03` — native scenario: measure adaptive attack success and residual risk rather than static checklist compliance
- `ELMOS_AI_ADVERSARIAL_ROBUSTNESS_EVASION_POISONING_CERTIFIER-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_ADVERSARIAL_ROBUSTNESS_EVASION_POISONING_CERTIFIER-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
