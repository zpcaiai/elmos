# Implementation Guide — AI Benchmark Grade Assurance Calibrator

## Purpose

Implement and independently certify ai benchmark grade assurance calibrator, including grade benchmark difficulty, realism, contamination resistance and statistical confidence, calibrate assurance claims to context complexity and evidence diversity and prevent leaderboard rank from becoming universal certification.

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

1. grade benchmark difficulty, realism, contamination resistance and statistical confidence
2. calibrate assurance claims to context complexity and evidence diversity
3. prevent leaderboard rank from becoming universal certification
4. bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
5. emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Native acceptance corpus

- `ELMOS_AI_BENCHMARK_GRADE_ASSURANCE_CALIBRATOR-01` — native scenario: grade benchmark difficulty, realism, contamination resistance and statistical confidence
- `ELMOS_AI_BENCHMARK_GRADE_ASSURANCE_CALIBRATOR-02` — native scenario: calibrate assurance claims to context complexity and evidence diversity
- `ELMOS_AI_BENCHMARK_GRADE_ASSURANCE_CALIBRATOR-03` — native scenario: prevent leaderboard rank from becoming universal certification
- `ELMOS_AI_BENCHMARK_GRADE_ASSURANCE_CALIBRATOR-04` — native scenario: bind every claim, method, decision rule and limitation to an exact RevisionSet and assurance profile
- `ELMOS_AI_BENCHMARK_GRADE_ASSURANCE_CALIBRATOR-05` — native scenario: emit independently reviewable evidence, uncertainty, competence and machine wall-clock/cost records

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
