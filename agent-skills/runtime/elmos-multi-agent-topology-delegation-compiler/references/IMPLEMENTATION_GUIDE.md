# Implementation Guide — Multi-Agent Topology and Delegation Compiler

## Purpose

Compile supervisor, peer, hierarchy, market and graph topologies with explicit responsibilities, delegation authority, state ownership and termination contracts.

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

1. Agent roles and responsibility matrix
2. Delegation depth and authority attenuation
3. Shared/private state ownership
4. Handoff and completion responsibility
5. Topology-specific termination criteria

## Native acceptance corpus

- `ELMOS_MULTI_AGENT_TOPOLOGY_DELEGATION_COMPILER-01` — supervisor-worker
- `ELMOS_MULTI_AGENT_TOPOLOGY_DELEGATION_COMPILER-02` — peer handoff
- `ELMOS_MULTI_AGENT_TOPOLOGY_DELEGATION_COMPILER-03` — delegation depth
- `ELMOS_MULTI_AGENT_TOPOLOGY_DELEGATION_COMPILER-04` — state ownership
- `ELMOS_MULTI_AGENT_TOPOLOGY_DELEGATION_COMPILER-05` — orphan task prevention
- `ELMOS_MULTI_AGENT_TOPOLOGY_DELEGATION_COMPILER-06` — termination path

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
