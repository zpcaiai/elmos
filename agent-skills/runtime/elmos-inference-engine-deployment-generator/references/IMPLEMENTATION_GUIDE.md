# Implementation Guide — Inference Engine Deployment Generator

## Purpose

Generate KServe, Triton, Ray Serve, vLLM, SGLang, TGI and equivalent deployments with exact images, model artifacts, probes, scaling and rollback.

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

1. select serving engine from workload profile
2. emit model repository and deployment manifests
3. configure health, readiness and startup probes
4. generate autoscaling, routing and cache policy
5. run native inference and rollback tests

## Native acceptance corpus

- `ELMOS_INFERENCE_ENGINE_DEPLOYMENT_GENERATOR-01` — native scenario: select serving engine from workload profile
- `ELMOS_INFERENCE_ENGINE_DEPLOYMENT_GENERATOR-02` — native scenario: emit model repository and deployment manifests
- `ELMOS_INFERENCE_ENGINE_DEPLOYMENT_GENERATOR-03` — native scenario: configure health, readiness and startup probes
- `ELMOS_INFERENCE_ENGINE_DEPLOYMENT_GENERATOR-04` — native scenario: generate autoscaling, routing and cache policy
- `ELMOS_INFERENCE_ENGINE_DEPLOYMENT_GENERATOR-05` — native scenario: run native inference and rollback tests

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
