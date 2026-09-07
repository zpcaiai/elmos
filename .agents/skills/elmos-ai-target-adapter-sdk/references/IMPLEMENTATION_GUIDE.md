# Implementation Guide — AITargetAdapterSdk

## Purpose

Define the only supported extension seam for target detection, capability profiling, lowering, emission, import, conformance, upgrade and evidence capture.

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

1. Define stable detect/import/lower/emit/validate SPI
2. Separate adapter capability from core authority
3. Require native conformance and exact version pins
4. Support adapter sandbox, upgrade and evidence invalidation

## Native acceptance corpus

- `ELMOS_AI_TARGET_ADAPTER_SDK-01` — valid adapter
- `ELMOS_AI_TARGET_ADAPTER_SDK-02` — missing capability
- `ELMOS_AI_TARGET_ADAPTER_SDK-03` — drifted adapter
- `ELMOS_AI_TARGET_ADAPTER_SDK-04` — AiTargetAdapterSdk representative end-to-end fixture
- `ELMOS_AI_TARGET_ADAPTER_SDK-05` — crash recovery preserves single-writer semantics
- `ELMOS_AI_TARGET_ADAPTER_SDK-06` — upstream or contract drift invalidates stale evidence
- `ELMOS_AI_TARGET_ADAPTER_SDK-07` — undeclared authority is denied
- `ELMOS_AI_TARGET_ADAPTER_SDK-08` — resource and wall-clock budget is measured
- `ELMOS_AI_TARGET_ADAPTER_SDK-09` — adapter manifest
- `ELMOS_AI_TARGET_ADAPTER_SDK-10` — capability negotiation

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
