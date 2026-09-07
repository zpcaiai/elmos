# Implementation Guide — API and SDK Code Generation Conformance Certifier

## Purpose

Generate and certify multi-language SDKs, examples and documentation from API/workflow contracts with compatibility, auth, error, streaming and retry semantics intact.

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

1. generate Java, Python, TypeScript, C#, Go and Rust clients
2. verify authentication, pagination, streaming and error models
3. run client-server contract and workflow tests
4. check source maps, documentation and semantic versioning
5. certify rollback and deprecation compatibility

## Native acceptance corpus

- `ELMOS_API_SDK_CODEGEN_CONFORMANCE_CERTIFIER-01` — native scenario: generate Java, Python, TypeScript, C#, Go and Rust clients
- `ELMOS_API_SDK_CODEGEN_CONFORMANCE_CERTIFIER-02` — native scenario: verify authentication, pagination, streaming and error models
- `ELMOS_API_SDK_CODEGEN_CONFORMANCE_CERTIFIER-03` — native scenario: run client-server contract and workflow tests
- `ELMOS_API_SDK_CODEGEN_CONFORMANCE_CERTIFIER-04` — native scenario: check source maps, documentation and semantic versioning
- `ELMOS_API_SDK_CODEGEN_CONFORMANCE_CERTIFIER-05` — native scenario: certify rollback and deprecation compatibility

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
