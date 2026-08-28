# Implementation Guide — Agent Memory Consolidation and Forgetting Controller

## Purpose

Consolidate episodic memory into semantic/procedural memory while preserving provenance, uncertainty, consent, retention and deliberate forgetting.

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

1. classify candidate memories by scope and purpose
2. deduplicate and consolidate with provenance
3. retain uncertainty and conflicting episodes
4. apply retention, consent and deletion
5. evaluate usefulness, bias and leakage before promotion

## Native acceptance corpus

- `ELMOS_AGENT_MEMORY_CONSOLIDATION_FORGETTING_CONTROLLER-01` — native scenario: classify candidate memories by scope and purpose
- `ELMOS_AGENT_MEMORY_CONSOLIDATION_FORGETTING_CONTROLLER-02` — native scenario: deduplicate and consolidate with provenance
- `ELMOS_AGENT_MEMORY_CONSOLIDATION_FORGETTING_CONTROLLER-03` — native scenario: retain uncertainty and conflicting episodes
- `ELMOS_AGENT_MEMORY_CONSOLIDATION_FORGETTING_CONTROLLER-04` — native scenario: apply retention, consent and deletion
- `ELMOS_AGENT_MEMORY_CONSOLIDATION_FORGETTING_CONTROLLER-05` — native scenario: evaluate usefulness, bias and leakage before promotion

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
