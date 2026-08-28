# Implementation Guide — Adversarial Model, Tool and Memory Red-Team Orchestrator

## Purpose

Coordinate multi-stage attacks across prompts, retrieval, memory, tools, protocols, identity and side effects with reproducible campaigns.

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

1. compose direct and indirect injection chains
2. attack tool schemas and delegation boundaries
3. poison memory and retrieval over time
4. exercise cross-agent and cross-protocol escalation
5. measure detection, containment and recovery

## Native acceptance corpus

- `ELMOS_ADVERSARIAL_MODEL_TOOL_MEMORY_REDTEAM_ORCHESTRATOR-01` — native scenario: compose direct and indirect injection chains
- `ELMOS_ADVERSARIAL_MODEL_TOOL_MEMORY_REDTEAM_ORCHESTRATOR-02` — native scenario: attack tool schemas and delegation boundaries
- `ELMOS_ADVERSARIAL_MODEL_TOOL_MEMORY_REDTEAM_ORCHESTRATOR-03` — native scenario: poison memory and retrieval over time
- `ELMOS_ADVERSARIAL_MODEL_TOOL_MEMORY_REDTEAM_ORCHESTRATOR-04` — native scenario: exercise cross-agent and cross-protocol escalation
- `ELMOS_ADVERSARIAL_MODEL_TOOL_MEMORY_REDTEAM_ORCHESTRATOR-05` — native scenario: measure detection, containment and recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
