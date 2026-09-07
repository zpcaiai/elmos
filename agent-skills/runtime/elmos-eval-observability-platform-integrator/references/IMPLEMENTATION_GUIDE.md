# Implementation Guide — Evaluation and Observability Platform Integrator

## Purpose

Integrate MLflow, Phoenix, LangSmith and OpenInference-compatible systems while retaining Elmos evidence, tenant, privacy and completion authority.

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

1. Bidirectional trace/dataset mapping
2. Platform capability negotiation
3. Tenant and privacy filtering
4. Experiment/evaluation synchronization
5. Export and vendor-exit validation

## Native acceptance corpus

- `ELMOS_EVAL_OBSERVABILITY_PLATFORM_INTEGRATOR-01` — MLflow mapping
- `ELMOS_EVAL_OBSERVABILITY_PLATFORM_INTEGRATOR-02` — Phoenix mapping
- `ELMOS_EVAL_OBSERVABILITY_PLATFORM_INTEGRATOR-03` — LangSmith mapping
- `ELMOS_EVAL_OBSERVABILITY_PLATFORM_INTEGRATOR-04` — OpenInference export
- `ELMOS_EVAL_OBSERVABILITY_PLATFORM_INTEGRATOR-05` — redaction
- `ELMOS_EVAL_OBSERVABILITY_PLATFORM_INTEGRATOR-06` — round-trip export

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
