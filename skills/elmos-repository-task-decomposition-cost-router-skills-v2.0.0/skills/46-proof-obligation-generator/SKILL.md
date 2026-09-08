---
name: elmos-proof-obligation-generator
version: 2.0.0
description: Translate requirements and invariants into executable or inspectable proof obligations attached to tasks and edges.
---

# Proof Obligation Generator

Define what must be proven before a task or boundary can be accepted.

## Inputs
- scenario graph
- invariant ledger
- task plan

## Outputs
- `proof obligations`
- `preferred verifier type`
- `evidence requirements`

## Procedure
1. Generate obligations for functional behavior, negative behavior, compatibility, security, migration, concurrency and side effects.
2. Prefer deterministic evidence: compiler, tests, static analyzers, executable probes and structured diffs.
3. Assign obligations to the smallest task or integration gate capable of proving them.
4. Mark obligations that require independent or repository-level verification.
5. Reject leaf completion when mandatory obligations remain open.

## Acceptance criteria
- every acceptance criterion and critical invariant maps to proof evidence

## Integration contract
- Read global configuration from `config/` and schemas from `schemas/`.
- Persist durable artifacts under `.elmos/runs/<run_id>/`.
- Any model invocation MUST pass through `elmos-model-registry-guard` and `elmos-cost-performance-router` unless this skill is itself the router/guard.
- Return structured evidence rather than a prose-only completion claim.
