# Implementation Guide — Model Quantization and Hardware Compatibility Certifier

## Purpose

Certify precision conversion, kernel availability, numerical quality, latency, memory, portability and fallback across accelerator targets.

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

1. profile FP32/BF16/FP16/INT8/low-bit variants
2. verify kernel and architecture support
3. measure task and safety quality deltas
4. benchmark memory, throughput and latency
5. gate fallback and dequantization paths

## Native acceptance corpus

- `ELMOS_MODEL_QUANTIZATION_HARDWARE_COMPATIBILITY_CERTIFIER-01` — native scenario: profile FP32/BF16/FP16/INT8/low-bit variants
- `ELMOS_MODEL_QUANTIZATION_HARDWARE_COMPATIBILITY_CERTIFIER-02` — native scenario: verify kernel and architecture support
- `ELMOS_MODEL_QUANTIZATION_HARDWARE_COMPATIBILITY_CERTIFIER-03` — native scenario: measure task and safety quality deltas
- `ELMOS_MODEL_QUANTIZATION_HARDWARE_COMPATIBILITY_CERTIFIER-04` — native scenario: benchmark memory, throughput and latency
- `ELMOS_MODEL_QUANTIZATION_HARDWARE_COMPATIBILITY_CERTIFIER-05` — native scenario: gate fallback and dequantization paths

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
