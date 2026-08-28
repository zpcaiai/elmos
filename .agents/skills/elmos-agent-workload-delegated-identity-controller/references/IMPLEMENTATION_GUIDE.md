# Implementation Guide — Agent Workload Delegated Identity Controller

## Purpose

Separate human, logical agent, runtime workload and downstream delegated identities using short-lived workload credentials and policy-bound token exchange.

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

1. Human-to-agent delegation chain
2. Workload attestation and short-lived identity
3. OAuth token exchange with audience binding
4. Environment/attachment authority binding
5. Credential rotation and compromise response

## Native acceptance corpus

- `ELMOS_AGENT_WORKLOAD_DELEGATED_IDENTITY_CONTROLLER-01` — valid attestation
- `ELMOS_AGENT_WORKLOAD_DELEGATED_IDENTITY_CONTROLLER-02` — unattested workload denial
- `ELMOS_AGENT_WORKLOAD_DELEGATED_IDENTITY_CONTROLLER-03` — delegation depth limit
- `ELMOS_AGENT_WORKLOAD_DELEGATED_IDENTITY_CONTROLLER-04` — wrong audience denial
- `ELMOS_AGENT_WORKLOAD_DELEGATED_IDENTITY_CONTROLLER-05` — credential rotation
- `ELMOS_AGENT_WORKLOAD_DELEGATED_IDENTITY_CONTROLLER-06` — revoked workload termination

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
