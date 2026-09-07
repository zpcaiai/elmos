# Implementation Guide — On-Device and Edge AI Project Generator

## Purpose

Generate Core ML, TensorFlow Lite, ONNX Runtime, llama.cpp and edge deployments with resource, privacy, update and offline behavior contracts.

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

1. profile device CPU/GPU/NPU and memory
2. convert and package portable model artifacts
3. generate offline-first data and tool behavior
4. implement signed staged model updates
5. test thermal, battery and degraded network envelopes

## Native acceptance corpus

- `ELMOS_ON_DEVICE_EDGE_AI_PROJECT_GENERATOR-01` — native scenario: profile device CPU/GPU/NPU and memory
- `ELMOS_ON_DEVICE_EDGE_AI_PROJECT_GENERATOR-02` — native scenario: convert and package portable model artifacts
- `ELMOS_ON_DEVICE_EDGE_AI_PROJECT_GENERATOR-03` — native scenario: generate offline-first data and tool behavior
- `ELMOS_ON_DEVICE_EDGE_AI_PROJECT_GENERATOR-04` — native scenario: implement signed staged model updates
- `ELMOS_ON_DEVICE_EDGE_AI_PROJECT_GENERATOR-05` — native scenario: test thermal, battery and degraded network envelopes

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
