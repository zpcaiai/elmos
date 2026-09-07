---
name: elmos-build-toolchain-discovery
description: "Recover build, package, runtime, test, code-generation, and native toolchain requirements for every module."
version: 1.0.0
skill_id: ELMOS-POLY-005
layer: build-analysis
risk: critical
readiness: not-run
dependencies:
  - "elmos-multi-source-repository-discovery"
triggers:
  - "Use when implementing or executing `elmos-build-toolchain-discovery`."
  - "Use when the current DAG node requires the build-analysis capability."
outputs:
  - "toolchain-inventory.json"
  - "build-graph.json"
  - "lockfile-status.json"
  - "reproduction-plan.md"
---

# Build Toolchain Discovery

## Objective

Recover build, package, runtime, test, code-generation, and native toolchain requirements for every module.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-build-toolchain-discovery`.
- Use when the current DAG node requires the build-analysis capability.

## Preconditions

- The repository or requirements input is bound to an immutable snapshot.
- Scope, authorization, data handling, model routing, runner, and secret policies are available.
- Dependency artifacts listed below are current and schema-valid.
- A clean worktree and checkpoint exist before any write.
- Readiness starts as `not-run`.

### Hard dependencies

- `elmos-multi-source-repository-discovery`

## Inputs

- `run_id` and immutable `snapshot_id`.
- authorized scope and execution policy.
- upstream machine-readable artifacts declared in the dependency graph.
- target profile or route decision when applicable.

## Outputs

- `toolchain-inventory.json`
- `build-graph.json`
- `lockfile-status.json`
- `reproduction-plan.md`

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Detect language versions, SDK constraints, compilers, package managers, plugins, build profiles, and platform targets.
2. Parse lockfiles and distinguish declared, resolved, optional, development, and transitive dependencies.
3. Recover code-generation steps and generated-artifact dependencies.
4. Map environment variables and secrets by name only; never copy values.
5. Detect non-hermetic downloads, mutable version ranges, local path dependencies, and unpinned images.
6. Create an offline or mirrored dependency plan where required.
7. Generate exact baseline build commands per module.
8. Record toolchain conflicts and unsupported platforms.

## Implementation Contract

- Use native package/build tooling in read-only or dry-run mode where possible.
- Record exact versions, platforms, lockfiles, and command lines.
- Do not auto-upgrade dependencies during discovery.

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

- [ ] Every build root has an executable or explicitly blocked reproduction plan..
- [ ] Mutable dependency versions are reported..
- [ ] Code generation runs before compilation in the recovered graph..
- [ ] No credential value is copied into output artifacts..

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
