# Implementation Guide — AI Synthetic Test and Simulation Generator

## Purpose

Generate privacy-safe synthetic scenarios, tool simulators, user personas and fault environments with measurable realism and coverage limits.

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

1. Scenario grammar and constraint generation
2. Tool/environment simulation
3. Rare/failure/adversarial case synthesis
4. Privacy and memorization checks
5. Realism and coverage comparison to holdout

## Native acceptance corpus

- `ELMOS_AI_SYNTHETIC_TEST_SIMULATION_GENERATOR-01` — constraint validity
- `ELMOS_AI_SYNTHETIC_TEST_SIMULATION_GENERATOR-02` — tool simulator determinism
- `ELMOS_AI_SYNTHETIC_TEST_SIMULATION_GENERATOR-03` — rare event coverage
- `ELMOS_AI_SYNTHETIC_TEST_SIMULATION_GENERATOR-04` — privacy similarity check
- `ELMOS_AI_SYNTHETIC_TEST_SIMULATION_GENERATOR-05` — realism comparison
- `ELMOS_AI_SYNTHETIC_TEST_SIMULATION_GENERATOR-06` — known limitation ledger

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
