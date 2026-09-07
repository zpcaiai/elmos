# Implementation Guide — Benchmark Contamination and Leakage Detector

## Purpose

Detect public, training, repository, prompt and evaluator contamination in hidden benchmarks and customer holdouts.

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

1. fingerprint benchmark content and provenance
2. scan source, prompts, caches and training artifacts
3. hold out variants and canary items
4. detect memorization and suspicious similarity
5. quarantine contaminated scores and recertify

## Native acceptance corpus

- `ELMOS_BENCHMARK_CONTAMINATION_LEAKAGE_DETECTOR-01` — native scenario: fingerprint benchmark content and provenance
- `ELMOS_BENCHMARK_CONTAMINATION_LEAKAGE_DETECTOR-02` — native scenario: scan source, prompts, caches and training artifacts
- `ELMOS_BENCHMARK_CONTAMINATION_LEAKAGE_DETECTOR-03` — native scenario: hold out variants and canary items
- `ELMOS_BENCHMARK_CONTAMINATION_LEAKAGE_DETECTOR-04` — native scenario: detect memorization and suspicious similarity
- `ELMOS_BENCHMARK_CONTAMINATION_LEAKAGE_DETECTOR-05` — native scenario: quarantine contaminated scores and recertify

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
