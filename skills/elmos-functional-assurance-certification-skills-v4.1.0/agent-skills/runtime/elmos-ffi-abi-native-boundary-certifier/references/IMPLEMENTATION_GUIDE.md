# Implementation Guide — FFI, ABI and Native Boundary Certifier

## Purpose

Model and certify calling conventions, layout, ownership, lifetime, error, thread and binary compatibility at JNI, P/Invoke, C ABI, WebAssembly and native-library boundaries.

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

1. fingerprint platform ABI and compiler flags
2. verify struct layout, alignment and symbol visibility
3. check ownership and lifetime transfer
4. exercise callback, exception and thread-affinity boundaries
5. certify binary compatibility and rollback

## Native acceptance corpus

- `ELMOS_FFI_ABI_NATIVE_BOUNDARY_CERTIFIER-01` — native scenario: fingerprint platform ABI and compiler flags
- `ELMOS_FFI_ABI_NATIVE_BOUNDARY_CERTIFIER-02` — native scenario: verify struct layout, alignment and symbol visibility
- `ELMOS_FFI_ABI_NATIVE_BOUNDARY_CERTIFIER-03` — native scenario: check ownership and lifetime transfer
- `ELMOS_FFI_ABI_NATIVE_BOUNDARY_CERTIFIER-04` — native scenario: exercise callback, exception and thread-affinity boundaries
- `ELMOS_FFI_ABI_NATIVE_BOUNDARY_CERTIFIER-05` — native scenario: certify binary compatibility and rollback

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
