---
name: elmos-full-project-generator
description: "Generate an entire production-oriented project from requirements by moving through executable specification, target architecture, code, tests, deployment, security, evidence, and readiness gates."
version: 1.0.0
skill_id: ELMOS-POLY-063
layer: product-entry
risk: critical
readiness: not-run
dependencies:
  - "elmos-polyglot-modernization-orchestrator"
  - "elmos-target-profile-designer"
  - "elmos-migration-dag-builder"
  - "elmos-compile-test-repair-loop"
  - "elmos-production-readiness-gate"
triggers:
  - "Use when implementing or executing `elmos-full-project-generator`."
  - "Use when the current DAG node requires the product-entry capability."
outputs:
  - "generation-run.json"
  - "generated-project/"
  - "generation-evidence/"
  - "project-handoff.md"
---

# Full Project Generator

## Objective

Generate an entire production-oriented project from requirements by moving through executable specification, target architecture, code, tests, deployment, security, evidence, and readiness gates.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-full-project-generator`.
- Use when the current DAG node requires the product-entry capability.

## Preconditions

- The repository or requirements input is bound to an immutable snapshot.
- Scope, authorization, data handling, model routing, runner, and secret policies are available.
- Dependency artifacts listed below are current and schema-valid.
- A clean worktree and checkpoint exist before any write.
- Readiness starts as `not-run`.

### Hard dependencies

- `elmos-polyglot-modernization-orchestrator`
- `elmos-target-profile-designer`
- `elmos-migration-dag-builder`
- `elmos-compile-test-repair-loop`
- `elmos-production-readiness-gate`

## Inputs

- `run_id` and immutable `snapshot_id`.
- authorized scope and execution policy.
- upstream machine-readable artifacts declared in the dependency graph.
- target profile or route decision when applicable.

## Outputs

- `generation-run.json`
- `generated-project/`
- `generation-evidence/`
- `project-handoff.md`

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Ingest PRD, user stories, domain rules, prototypes, API/schema constraints, non-functional requirements, and delivery policies.
2. Normalize ambiguous requirements into a requirements graph with assumptions, open decisions, acceptance tests, and explicit exclusions.
3. Choose a target profile only from the user-approved technology set and versions.
4. Generate domain, data, API, UI, security, integration, deployment, observability, and operations architecture with ADRs.
5. Create a migration-style DAG even for greenfield generation so every module has inputs, tests, dependencies, checkpoints, and ownership.
6. Generate repository structure, code, schemas, migrations, SDKs, tests, fixtures, CI/CD, containers, infrastructure, documentation, and runbooks.
7. Run toolchain provisioning, clean builds, contract/integration/end-to-end/security/performance tests, and bounded repair loops.
8. Reject placeholder-only modules, fake integrations, disabled tests, hard-coded secrets, and undocumented mocks.
9. Package evidence and issue readiness as not-run, blocked, fail, waived, or pass strictly from executed checks.
10. Deliver a clean, reproducible repository and completion report.

## Implementation Contract

- The entry skill orchestrates shared capabilities; it must not duplicate hidden implementation logic.
- Generated or transformed files are not proof of build, behavior, security, or production readiness.
- Every claim must point to executed evidence.

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

- [ ] A representative sample specification generates a clean repository..
- [ ] Every declared feature maps to code and acceptance tests or an explicit exclusion..
- [ ] Clean checkout builds and tests with documented commands..
- [ ] No TODO, stub, fake success, or hard-coded secret is accepted in production scope..
- [ ] Readiness remains not-run until real execution evidence exists..

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
