# Implementation Guide — Inference Cache, Prefix and KV Consistency Controller

## Purpose

Govern prompt/result/prefix/KV caches with exact key semantics, tenant isolation, model/version binding, invalidation and quality evidence.

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

1. derive canonical cache keys and context boundaries
2. bind cache entries to model, prompt, tool and policy digests
3. verify tenant and residency isolation
4. coordinate KV offload and eviction
5. measure hit rate without stale semantic reuse

## Native acceptance corpus

- `ELMOS_INFERENCE_CACHE_PREFIX_KV_CONSISTENCY_CONTROLLER-01` — native scenario: derive canonical cache keys and context boundaries
- `ELMOS_INFERENCE_CACHE_PREFIX_KV_CONSISTENCY_CONTROLLER-02` — native scenario: bind cache entries to model, prompt, tool and policy digests
- `ELMOS_INFERENCE_CACHE_PREFIX_KV_CONSISTENCY_CONTROLLER-03` — native scenario: verify tenant and residency isolation
- `ELMOS_INFERENCE_CACHE_PREFIX_KV_CONSISTENCY_CONTROLLER-04` — native scenario: coordinate KV offload and eviction
- `ELMOS_INFERENCE_CACHE_PREFIX_KV_CONSISTENCY_CONTROLLER-05` — native scenario: measure hit rate without stale semantic reuse

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
