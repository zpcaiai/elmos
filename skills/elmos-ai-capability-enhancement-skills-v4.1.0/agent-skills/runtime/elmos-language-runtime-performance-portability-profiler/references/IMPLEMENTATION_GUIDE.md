# Implementation Guide — Language Runtime Performance Portability Profiler

## Purpose

Characterize latency, throughput, startup, memory, GC, scheduling and native-image behavior so route selection reflects runtime economics rather than syntax alone.

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

1. benchmark representative workload envelopes
2. separate cold start from steady state
3. profile GC, allocator and scheduler effects
4. compare native/AOT/JIT deployment modes
5. produce capacity and cost portability model

## Native acceptance corpus

- `ELMOS_LANGUAGE_RUNTIME_PERFORMANCE_PORTABILITY_PROFILER-01` — native scenario: benchmark representative workload envelopes
- `ELMOS_LANGUAGE_RUNTIME_PERFORMANCE_PORTABILITY_PROFILER-02` — native scenario: separate cold start from steady state
- `ELMOS_LANGUAGE_RUNTIME_PERFORMANCE_PORTABILITY_PROFILER-03` — native scenario: profile GC, allocator and scheduler effects
- `ELMOS_LANGUAGE_RUNTIME_PERFORMANCE_PORTABILITY_PROFILER-04` — native scenario: compare native/AOT/JIT deployment modes
- `ELMOS_LANGUAGE_RUNTIME_PERFORMANCE_PORTABILITY_PROFILER-05` — native scenario: produce capacity and cost portability model

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
