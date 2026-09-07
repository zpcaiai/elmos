---
name: elmos-agentic-execution-runtime
description: Execute repository tasks through isolated, typed, supervised, dependency-aware proof workers.
priority: P0
---

# K4 — Agentic Execution & Workspace Isolation

## Skills

- agent-definition-ir
- agent-capability-registry
- agent-discovery
- agent-policy-resolution
- spawn-policy
- recursion-depth-governor
- self-recursion-guard
- tool-authority-profile
- agent-model-policy
- effort-ceiling
- autoload-skill-policy
- read-summary-policy
- prewalk-agent
- phase-model-handoff
- isolated-workspace
- workspace-owner
- workspace-lease
- workspace-fence
- workspace-snapshot
- typed-agent-yield
- proof-carrying-result
- agent-task-dag
- blocking-vs-async-policy
- agent-supervisor
- steer-agent
- park-revive-agent
- kill-release-agent
- child-lineage
- merge-coordinator
- orphan-agent-reaper

## Required improvement over local-agent designs

- project/user/bundled agent collisions MUST be namespace/version aware;
- production tasks MUST default to strict schema;
- write-capable siblings MUST NOT share an unfenced workspace;
- model fallback MUST preserve effort/security ceilings;
- revival MUST restore authority profile and ownership, not only transcript;
- task DAG state MUST be durable independently of model sessions.

## Agent state

CREATED → READY → RUNNING → WAITING → PARKED → SUCCEEDED
                                   ↘ FAILED / ABORTED / QUARANTINED

## Acceptance

- no unauthorized spawn;
- no cross-workspace write leak;
- no merge without ownership/fence validation;
- child outputs are machine-validated before parent consumption;
- agent death can be recovered without replaying already committed side effects.
