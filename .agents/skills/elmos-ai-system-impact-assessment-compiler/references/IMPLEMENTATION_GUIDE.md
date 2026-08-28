# Implementation Guide — AI System Impact Assessment Compiler

## Purpose

Compile lifecycle impact assessments covering affected people, rights, safety, accessibility, environment, misuse, distributional effects and mitigation ownership.

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

1. Define intended use and reasonably foreseeable misuse
2. Identify affected stakeholders and impact pathways
3. Evaluate severity, likelihood, reversibility and distribution
4. Bind technical/organizational mitigations and monitoring
5. Require independent/human review for material impacts

## Native acceptance corpus

- `ELMOS_AI_SYSTEM_IMPACT_ASSESSMENT_COMPILER-01` — intended-use assessment
- `ELMOS_AI_SYSTEM_IMPACT_ASSESSMENT_COMPILER-02` — misuse scenario
- `ELMOS_AI_SYSTEM_IMPACT_ASSESSMENT_COMPILER-03` — vulnerable stakeholder
- `ELMOS_AI_SYSTEM_IMPACT_ASSESSMENT_COMPILER-04` — accessibility impact
- `ELMOS_AI_SYSTEM_IMPACT_ASSESSMENT_COMPILER-05` — human oversight adequacy
- `ELMOS_AI_SYSTEM_IMPACT_ASSESSMENT_COMPILER-06` — post-deployment impact review

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
