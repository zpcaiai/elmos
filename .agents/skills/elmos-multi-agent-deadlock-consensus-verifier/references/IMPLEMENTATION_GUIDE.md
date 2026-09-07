# Implementation Guide — Multi-Agent Deadlock and Consensus Verifier

## Purpose

Verify multi-agent workflows for deadlock, livelock, split-brain, contradictory decisions, duplicate work and bounded consensus behavior.

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

1. Wait-for and dependency graph analysis
2. State-machine liveness/model checking
3. Conflict resolution and quorum semantics
4. Duplicate work and side-effect detection
5. Counterexample minimization

## Native acceptance corpus

- `ELMOS_MULTI_AGENT_DEADLOCK_CONSENSUS_VERIFIER-01` — acyclic completion
- `ELMOS_MULTI_AGENT_DEADLOCK_CONSENSUS_VERIFIER-02` — deadlock fixture
- `ELMOS_MULTI_AGENT_DEADLOCK_CONSENSUS_VERIFIER-03` — livelock fixture
- `ELMOS_MULTI_AGENT_DEADLOCK_CONSENSUS_VERIFIER-04` — split-brain decision
- `ELMOS_MULTI_AGENT_DEADLOCK_CONSENSUS_VERIFIER-05` — duplicate task
- `ELMOS_MULTI_AGENT_DEADLOCK_CONSENSUS_VERIFIER-06` — quorum timeout

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
