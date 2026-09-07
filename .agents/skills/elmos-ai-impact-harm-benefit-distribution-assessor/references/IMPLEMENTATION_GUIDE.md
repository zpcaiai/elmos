# Implementation Guide — AI Impact, Harm and Benefit Distribution Assessor

## Purpose

Implement and independently certify ai impact, harm and benefit distribution assessor, including identify direct, indirect, cumulative and systemic impacts across lifecycle, compare benefits and harms across individuals, groups, operators and society and record foreseeable misuse, affected rights and mitigation ownership.

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

1. identify direct, indirect, cumulative and systemic impacts across lifecycle
2. compare benefits and harms across individuals, groups, operators and society
3. record foreseeable misuse, affected rights and mitigation ownership
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_IMPACT_HARM_BENEFIT_DISTRIBUTION_ASSESSOR-01` — native scenario: identify direct, indirect, cumulative and systemic impacts across lifecycle
- `ELMOS_AI_IMPACT_HARM_BENEFIT_DISTRIBUTION_ASSESSOR-02` — native scenario: compare benefits and harms across individuals, groups, operators and society
- `ELMOS_AI_IMPACT_HARM_BENEFIT_DISTRIBUTION_ASSESSOR-03` — native scenario: record foreseeable misuse, affected rights and mitigation ownership
- `ELMOS_AI_IMPACT_HARM_BENEFIT_DISTRIBUTION_ASSESSOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_IMPACT_HARM_BENEFIT_DISTRIBUTION_ASSESSOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
