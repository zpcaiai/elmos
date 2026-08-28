# Implementation Guide — AI Provider Behavior Fingerprint Recertifier

## Purpose

Fingerprint model/provider behavior with versioned probes and invalidate evidence when tool calling, schema compliance, safety, latency or accounting drifts.

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

1. Resolved model/version and region capture
2. Tool-call and structured-output probes
3. Safety/refusal/cache/accounting fingerprint
4. Distributional drift thresholds
5. Evidence invalidation and recertification workflow

## Native acceptance corpus

- `ELMOS_AI_PROVIDER_BEHAVIOR_FINGERPRINT_RECERTIFIER-01` — stable baseline
- `ELMOS_AI_PROVIDER_BEHAVIOR_FINGERPRINT_RECERTIFIER-02` — tool-call drift
- `ELMOS_AI_PROVIDER_BEHAVIOR_FINGERPRINT_RECERTIFIER-03` — schema drift
- `ELMOS_AI_PROVIDER_BEHAVIOR_FINGERPRINT_RECERTIFIER-04` — latency distribution drift
- `ELMOS_AI_PROVIDER_BEHAVIOR_FINGERPRINT_RECERTIFIER-05` — token-accounting drift
- `ELMOS_AI_PROVIDER_BEHAVIOR_FINGERPRINT_RECERTIFIER-06` — safety behavior drift

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
