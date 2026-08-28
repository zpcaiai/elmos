# Implementation Guide — Zero-Trust Service Identity Policy Compiler

## Purpose

Compile workload identity, mTLS, audience, delegation, authorization and rotation policies for agents, tools, services and customer runners.

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

1. map human, agent, workload and service identities
2. issue least-privilege audience-bound credentials
3. generate mTLS and authorization policy
4. rotate and revoke without downtime
5. verify cross-tenant and confused-deputy resistance

## Native acceptance corpus

- `ELMOS_ZERO_TRUST_SERVICE_IDENTITY_POLICY_COMPILER-01` — native scenario: map human, agent, workload and service identities
- `ELMOS_ZERO_TRUST_SERVICE_IDENTITY_POLICY_COMPILER-02` — native scenario: issue least-privilege audience-bound credentials
- `ELMOS_ZERO_TRUST_SERVICE_IDENTITY_POLICY_COMPILER-03` — native scenario: generate mTLS and authorization policy
- `ELMOS_ZERO_TRUST_SERVICE_IDENTITY_POLICY_COMPILER-04` — native scenario: rotate and revoke without downtime
- `ELMOS_ZERO_TRUST_SERVICE_IDENTITY_POLICY_COMPILER-05` — native scenario: verify cross-tenant and confused-deputy resistance

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
