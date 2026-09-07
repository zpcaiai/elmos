# Implementation Guide — Golden Route: Continuous Agent Certification

## Purpose

Certify the loop from privacy-filtered production traces to versioned evals, calibrated judges, behavior fingerprints, shadow rollout and recertification.

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

1. Trace-to-counterexample curation
2. Dataset and judge governance
3. Provider fingerprint baseline
4. No-side-effect shadow and canary
5. Drift invalidation and rollback

## Native acceptance corpus

- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-01` — trace privacy filter
- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-02` — counterexample promotion
- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-03` — judge calibration
- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-04` — provider drift
- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-05` — shadow no-write
- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-06` — automatic rollback
- `ELMOS_AI_GOLDEN_ROUTE_CONTINUOUS_AGENT_CERTIFICATION-07` — recertification

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
