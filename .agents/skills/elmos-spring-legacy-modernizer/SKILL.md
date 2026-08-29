---
name: elmos-spring-legacy-modernizer
description: "Modernize legacy Spring systems through inventory, characterization, Java and Spring upgrade, Jakarta migration, configuration/security/data refactoring, modularization, observability, deployment, and production evidence."
version: 1.0.0
skill_id: ELMOS-POLY-064
layer: product-entry
risk: critical
readiness: not-run
dependencies:
  - "elmos-adapter-java"
  - "elmos-polyglot-modernization-orchestrator"
  - "elmos-transformation-rule-dsl-author"
  - "elmos-compile-test-repair-loop"
  - "elmos-production-readiness-gate"
triggers:
  - "Use when implementing or executing `elmos-spring-legacy-modernizer`."
  - "Use when the current DAG node requires the product-entry capability."
outputs:
  - "spring-modernization-run.json"
  - "modernized-project/"
  - "spring-risk-register.json"
  - "spring-modernization-evidence/"
---

# Spring Legacy Modernizer

## Objective

Modernize legacy Spring systems through inventory, characterization, Java and Spring upgrade, Jakarta migration, configuration/security/data refactoring, modularization, observability, deployment, and production evidence.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-spring-legacy-modernizer`.
- Use when the current DAG node requires the product-entry capability.

## Preconditions

- The repository or requirements input is bound to an immutable snapshot.
- Scope, authorization, data handling, model routing, runner, and secret policies are available.
- Dependency artifacts listed below are current and schema-valid.
- A clean worktree and checkpoint exist before any write.
- Readiness starts as `not-run`.

### Hard dependencies

- `elmos-adapter-java`
- `elmos-polyglot-modernization-orchestrator`
- `elmos-transformation-rule-dsl-author`
- `elmos-compile-test-repair-loop`
- `elmos-production-readiness-gate`

## Inputs

- `run_id` and immutable `snapshot_id`.
- authorized scope and execution policy.
- upstream machine-readable artifacts declared in the dependency graph.
- target profile or route decision when applicable.

## Outputs

- `spring-modernization-run.json`
- `modernized-project/`
- `spring-risk-register.json`
- `spring-modernization-evidence/`

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Create an immutable source and runtime baseline for Java, Spring, build, API, data, performance, security, and deployment behavior.
2. Inventory Spring Framework/Boot/Cloud/Security/Data/Batch/Integration versions, XML/Java/annotation configuration, custom starters, servlet container, and Java/JDK constraints.
3. Select an incremental target route such as in-place upgrade, modular monolith, strangler migration, service extraction, or cross-stack conversion.
4. Upgrade build plugins and JDK in supported increments; keep each step buildable and reversible.
5. Migrate deprecated APIs and javax.* to jakarta.* only with dependency and runtime compatibility evidence.
6. Translate XML configuration, bean scopes, lifecycle, properties, validation, MVC, Security, JPA/Hibernate/MyBatis, transactions, messaging, scheduling, and tests.
7. Recover and preserve security filter ordering, transaction boundaries, serialization, error contracts, proxy/self-invocation behavior, lazy loading, and thread-local context.
8. Add container/runtime hardening, health probes, OpenTelemetry, SBOM, dependency governance, and rollback/canary plans.
9. Run compile-test-repair loops plus differential API/data/performance/security validation.
10. Issue a bounded readiness certificate and delivery handoff without claiming production success from static transformation alone.

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

- [ ] Legacy sample upgrades through at least two version boundaries..
- [ ] javax/jakarta, Security, Hibernate/JPA, proxy, transaction, and serialization fixtures are covered..
- [ ] Baseline old-client/new-service contract tests pass or versioned differences are approved..
- [ ] Rollback and data compatibility windows are tested..
- [ ] Readiness defaults to not-run and cannot pass from generated files alone..

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
