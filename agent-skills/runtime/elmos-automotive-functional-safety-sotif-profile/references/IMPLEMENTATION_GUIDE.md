# Implementation Guide — Automotive Functional Safety and SOTIF Profile

## Purpose

Implement and independently certify automotive functional safety and sotif profile, including compile item definition, HARA, safety goals, ASIL decomposition and safety case, evaluate intended-functionality insufficiency, perception limits and triggering conditions and link simulation, proving-ground, field monitoring and software update evidence.

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

1. compile item definition, HARA, safety goals, ASIL decomposition and safety case
2. evaluate intended-functionality insufficiency, perception limits and triggering conditions
3. link simulation, proving-ground, field monitoring and software update evidence
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AUTOMOTIVE_FUNCTIONAL_SAFETY_SOTIF_PROFILE-01` — native scenario: compile item definition, HARA, safety goals, ASIL decomposition and safety case
- `ELMOS_AUTOMOTIVE_FUNCTIONAL_SAFETY_SOTIF_PROFILE-02` — native scenario: evaluate intended-functionality insufficiency, perception limits and triggering conditions
- `ELMOS_AUTOMOTIVE_FUNCTIONAL_SAFETY_SOTIF_PROFILE-03` — native scenario: link simulation, proving-ground, field monitoring and software update evidence
- `ELMOS_AUTOMOTIVE_FUNCTIONAL_SAFETY_SOTIF_PROFILE-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AUTOMOTIVE_FUNCTIONAL_SAFETY_SOTIF_PROFILE-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
