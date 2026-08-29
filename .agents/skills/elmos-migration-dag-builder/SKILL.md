---
name: elmos-migration-dag-builder
description: "Turn the selected route into an executable, resumable, dependency-safe migration DAG with acceptance gates."
version: 1.0.0
skill_id: ELMOS-POLY-016
layer: planning
risk: critical
readiness: not-run
dependencies:
  - "elmos-migration-route-planner"
triggers:
  - "Use when implementing or executing `elmos-migration-dag-builder`."
  - "Use when the current DAG node requires the planning capability."
outputs:
  - "migration-dag.json"
  - "work-packages/"
  - "checkpoint-plan.json"
  - "rollback-plan.json"
---

# Migration Dag Builder

## Objective

Turn the selected route into an executable, resumable, dependency-safe migration DAG with acceptance gates.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-migration-dag-builder`.
- Use when the current DAG node requires the planning capability.

## Preconditions

- The repository or requirements input is bound to an immutable snapshot.
- Scope, authorization, data handling, model routing, runner, and secret policies are available.
- Dependency artifacts listed below are current and schema-valid.
- A clean worktree and checkpoint exist before any write.
- Readiness starts as `not-run`.

### Hard dependencies

- `elmos-migration-route-planner`

## Inputs

- `run_id` and immutable `snapshot_id`.
- authorized scope and execution policy.
- upstream machine-readable artifacts declared in the dependency graph.
- target profile or route decision when applicable.

## Outputs

- `migration-dag.json`
- `work-packages/`
- `checkpoint-plan.json`
- `rollback-plan.json`

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Decompose work by module, contract, data boundary, UI slice, integration, and deployment unit.
2. Order prerequisites such as toolchains, schemas, shared libraries, compatibility layers, and test harnesses.
3. Separate deterministic transforms, bounded agent changes, manual decisions, and external approvals.
4. Attach inputs, outputs, policies, resource limits, retries, idempotency keys, and acceptance tests to every node.
5. Insert checkpoints before side effects and irreversible actions.
6. Define rollback or compensating action for each deployable node.
7. Calculate critical path and parallel-safe groups.
8. Validate acyclicity and completeness.

## Implementation Contract

- Plans bind to exact snapshot, IR versions, target profile, and policies.
- Every work item has inputs, outputs, tests, and rollback/idempotency metadata.
- Unknowns lower confidence and create probes; they never become silent assumptions.

### Required implementation properties

- Expose the capability through a stable service or CLI boundary; avoid embedding orchestration inside prompts.
- Keep machine-readable artifacts deterministic where ordering has no semantic meaning.
- Version schemas, rules, adapters, and evidence producers.
- Persist provenance for every decision, patch, generated file, test, and gate.
- Make writes transactional or checkpointed and make retries idempotent.
- Store actual source and generated artifacts outside model messages; pass bounded references and excerpts.
- Emit structured diagnostics instead of converting unknowns into plausible code.
- Support cancellation and recovery without depending on the original client connection.

## Required Tests

- [ ] The DAG is acyclic..
- [ ] Every side-effecting node has an idempotency key..
- [ ] Every deployable node has rollback or explicit non-reversibility approval..
- [ ] Every node has verifiable outputs..

- [ ] Unauthorized path, command, network, and secret-access tests.
- [ ] Interrupted-run checkpoint and idempotent retry test.
- [ ] Stale snapshot/evidence rejection test.
- [ ] Schema validation and deterministic serialization test.
- [ ] Negative test proving missing execution evidence remains `not-run` or `blocked`.

## Verification

1. Validate all emitted JSON/YAML against the package schemas.
2. Re-run the skill on a clean checkpoint to verify reproducibility or documented nondeterminism.
3. Check that every output references the current snapshot and run.
4. Run required native toolchain tests in the trusted sandbox.
5. Attach command, exit code, environment identity, logs, and artifact hashes to evidence.

A successful verification result must state the exact scope. It must not imply that unrelated routes, platforms, frameworks, or production environments are certified.

## Stop and Escalate

- Required authorization, snapshot, dependency artifact, or toolchain is missing or stale.
- A change would cross an undeclared trust, data, module, or deployment boundary.
- Semantic loss affects security, money, data integrity, concurrency, public contracts, or irreversible state without owner approval.
- The retry, time, resource, or patch budget is exhausted.
- Verification cannot distinguish target behavior from an unsupported assumption.

When stopping, preserve the last safe checkpoint and return a structured blocker with owner, evidence, affected scope, safe alternatives, and the exact decision needed.

## Definition of Done

- [ ] Implementation code exists behind the declared stable interface.
- [ ] Required schemas, migrations, policies, and configuration are versioned.
- [ ] Unit, integration, negative, security, recovery, and representative end-to-end tests pass.
- [ ] Native toolchain commands run successfully in a clean trusted sandbox.
- [ ] Evidence links every material claim to current outputs.
- [ ] Residual semantic losses and unsupported cases are explicit.
- [ ] Documentation covers setup, operation, failure recovery, and extension.
- [ ] Readiness state is derived from executed gates and is never inferred from file presence.

## Completion Report

Return a machine-readable report and a human summary containing:

- run ID, snapshot ID, target profile, route, and skill version.
- files and artifacts created, changed, or intentionally left unchanged.
- commands executed with exit codes and environment identity.
- tests and gates by pass/fail/blocked/waived/not-run.
- semantic losses, residual risks, assumptions, and required approvals.
- next executable work items and rollback/checkpoint location.

End the report with one of: `completed`, `completed-with-approved-exceptions`, `blocked`, or `failed`. Never use `completed` when any required gate is `not-run`.
