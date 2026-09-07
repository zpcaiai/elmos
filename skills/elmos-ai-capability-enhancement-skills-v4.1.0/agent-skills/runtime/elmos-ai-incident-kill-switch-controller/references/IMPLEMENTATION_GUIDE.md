# Implementation Guide — AI Incident Kill Switch Controller

## Purpose

Execute tenant, agent, tool, provider, Skill, prompt, memory and credential shutdown while preserving evidence and reconciling active side effects.

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

1. Hierarchical kill-switch scopes
2. Active run cancellation and fencing
3. Tool/credential revocation
4. Memory quarantine and evidence preservation
5. Safe restart and recertification gate

## Native acceptance corpus

- `ELMOS_AI_INCIDENT_KILL_SWITCH_CONTROLLER-01` — tenant stop
- `ELMOS_AI_INCIDENT_KILL_SWITCH_CONTROLLER-02` — tool revocation
- `ELMOS_AI_INCIDENT_KILL_SWITCH_CONTROLLER-03` — provider circuit break
- `ELMOS_AI_INCIDENT_KILL_SWITCH_CONTROLLER-04` — active run cancellation
- `ELMOS_AI_INCIDENT_KILL_SWITCH_CONTROLLER-05` — memory quarantine
- `ELMOS_AI_INCIDENT_KILL_SWITCH_CONTROLLER-06` — safe restart denial/pass

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
