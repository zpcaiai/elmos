# Implementation Guide — WASI Sandbox and Capability Certifier

## Purpose

Certify filesystem, network, clock, randomness, environment, secret and process capabilities for WASI workloads under deny-by-default runtime policy.

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

1. compile explicit WASI capability grants
2. deny undeclared filesystem and network access
3. virtualize clock and randomness for replay
4. verify host-call audit and tenant isolation
5. exercise revocation, timeout and escape negative cases

## Native acceptance corpus

- `ELMOS_WASI_SANDBOX_CAPABILITY_CERTIFIER-01` — native scenario: compile explicit WASI capability grants
- `ELMOS_WASI_SANDBOX_CAPABILITY_CERTIFIER-02` — native scenario: deny undeclared filesystem and network access
- `ELMOS_WASI_SANDBOX_CAPABILITY_CERTIFIER-03` — native scenario: virtualize clock and randomness for replay
- `ELMOS_WASI_SANDBOX_CAPABILITY_CERTIFIER-04` — native scenario: verify host-call audit and tenant isolation
- `ELMOS_WASI_SANDBOX_CAPABILITY_CERTIFIER-05` — native scenario: exercise revocation, timeout and escape negative cases

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
