# Implementation Guide — WebAssembly Component and WIT Portability Compiler

## Purpose

Compile polyglot components, worlds, interfaces, resources, ownership and canonical ABI contracts into portable WebAssembly Component Model artifacts with native round-trip evidence.

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

1. compile WIT worlds, interfaces and resource ownership
2. lower language types through canonical ABI mappings
3. generate component composition and version contracts
4. verify cross-language component round trips
5. certify host/guest rollback and unsupported-feature blocking

## Native acceptance corpus

- `ELMOS_WASM_COMPONENT_WIT_PORTABILITY_COMPILER-01` — native scenario: compile WIT worlds, interfaces and resource ownership
- `ELMOS_WASM_COMPONENT_WIT_PORTABILITY_COMPILER-02` — native scenario: lower language types through canonical ABI mappings
- `ELMOS_WASM_COMPONENT_WIT_PORTABILITY_COMPILER-03` — native scenario: generate component composition and version contracts
- `ELMOS_WASM_COMPONENT_WIT_PORTABILITY_COMPILER-04` — native scenario: verify cross-language component round trips
- `ELMOS_WASM_COMPONENT_WIT_PORTABILITY_COMPILER-05` — native scenario: certify host/guest rollback and unsupported-feature blocking

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
