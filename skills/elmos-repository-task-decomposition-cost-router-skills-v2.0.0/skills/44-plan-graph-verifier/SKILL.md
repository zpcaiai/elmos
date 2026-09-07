---
name: elmos-plan-graph-verifier
version: 2.0.0
description: Structurally validate hierarchical plans and DAG edges before execution using deterministic graph checks and typed contracts.
---

# Plan Graph Verifier

Verify planning structure before spending model budget on implementation.

## Inputs
- hierarchical plan
- execution DAG
- scenario graph
- invariant ledger
- task contracts

## Outputs
- `plan verification report`
- `node risks`
- `edge risks`
- `repair suggestions`

## Procedure
1. Reject cycles, orphan nodes, missing prerequisites and impossible readiness states.
2. Check producer/consumer type and schema compatibility on every dependency edge.
3. Check that every cross-task edge has a handoff contract and validation method.
4. Verify all acceptance scenarios and critical invariants have complete task/evidence coverage.
5. Detect path ownership overlaps, hidden shared-state coupling and unsupported parallel waves.
6. Apply local graph repairs first: insert bridge task, merge nodes, split node, add missing edge or move integration gate.

## Guardrails
- An LLM prose review cannot override failed deterministic structural checks.

## Acceptance criteria
- graph is executable, acyclic and acceptance-complete
- all critical edge risks are resolved or explicitly waived

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
