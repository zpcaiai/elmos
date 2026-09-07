# ADR-0024: Bounded agent repair control loop

- Status: Accepted
- Date: 2026-07-21

## Decision

Agent repair is a failure-to-task-to-route-to-patch-to-independent-validation loop. Provider identity is not a user-facing model picker. Routing first applies hard filters for data residency, repository sensitivity, tool needs, risk, context capacity and a pre-reserved budget; only eligible providers are ranked.

The Agent Gateway produces policy-bound plans for Codex, Claude and OpenHands. Plans are non-interactive, deny network and SCM mutation, never mount a Docker socket, and separate the editing workspace from the fresh validation workspace. The control plane and Agent Gateway do not invoke host processes. Codex plans use its documented non-interactive execution shape; Claude plans include pre-tool denial policy; OpenHands plans require an isolated container sandbox.

An agent cannot declare success. Scope limits, anti-cheating checks, an independent build/test result, measurable progress, attempt ceilings, budget ceilings and tree-hash oscillation determine the next action. Critical risk, legal ambiguity, no provider, repeated no-progress or exhausted attempts produce an evidence-rich human escalation.

## Consequences

Provider execution is intentionally fail-closed until an isolated runner is configured. Missing usage is charged conservatively instead of treated as free.
