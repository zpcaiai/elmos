---
name: elmos-adapter-react
description: "Implement React-specific UI analysis and conversion for components, hooks, state, routing, forms, styling, SSR/RSC, accessibility, and user journeys."
version: 1.0.0
skill_id: ELMOS-POLY-058
layer: technology-adapter
risk: critical
readiness: not-run
dependencies:
  - "elmos-build-toolchain-discovery"
triggers:
  - "Use when implementing or executing `elmos-adapter-react`."
  - "Use when the current DAG node requires the technology-adapter capability."
  - "Use when `react` is a source, target, interoperability, or modernization technology."
  - "Use when files or build roots matching .jsx, .tsx, .js, .ts are detected."
outputs:
  - "adapters/react/adapter-manifest.json"
  - "adapters/react/parser-profile.yaml"
  - "adapters/react/semantic-mapping.yaml"
  - "adapters/react/verification-profile.yaml"
---

# Adapter React

## Objective

Implement React-specific UI analysis and conversion for components, hooks, state, routing, forms, styling, SSR/RSC, accessibility, and user journeys.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-adapter-react`.
- Use when the current DAG node requires the technology-adapter capability.
- Use when `react` is a source, target, interoperability, or modernization technology.
- Use when files or build roots matching .jsx, .tsx, .js, .ts are detected.

## Preconditions

- The repository or requirements input is bound to an immutable snapshot.
- Scope, authorization, data handling, model routing, runner, and secret policies are available.
- Dependency artifacts listed below are current and schema-valid.
- A clean worktree and checkpoint exist before any write.
- Readiness starts as `not-run`.

### Hard dependencies

- `elmos-build-toolchain-discovery`

## Inputs

- `run_id` and immutable `snapshot_id`.
- authorized scope and execution policy.
- upstream machine-readable artifacts declared in the dependency graph.
- target profile or route decision when applicable.
- Technology registry entry `react` and the detected native toolchain profile.

## Outputs

- `adapters/react/adapter-manifest.json`
- `adapters/react/parser-profile.yaml`
- `adapters/react/semantic-mapping.yaml`
- `adapters/react/verification-profile.yaml`

## Technology profile

| Field | Value |
|---|---|
| Registry ID | `react` |
| Display name | React |
| Kind | framework |
| File/build markers | `.jsx`, `.tsx`, `.js`, `.ts` |
| Build systems | Vite, Next.js, Webpack, Rspack, Turbopack |
| Preferred analyzers | TypeScript Compiler API, Babel, jscodeshift, ts-morph |
| Framework coverage | React, Next.js, React Router, Redux, TanStack Query |
| Native verification | `vitest`, `jest`, `React Testing Library`, `Playwright`, `axe-core` |

### Semantic risk register

- hook ordering and closure capture.
- effects and cleanup timing.
- server/client component boundaries.
- state/cache ownership.
- hydration and SSR divergence.
- render concurrency.
- accessibility and focus behavior.

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Detect React, Next.js, router, state, query, form, styling, component library, build, test, and rendering modes.
2. Use TypeScript/Babel AST to map components, props, contexts, hooks, effects, refs, memoization, boundaries, routes, and data dependencies.
3. Build Framework IR for component tree, state ownership, server/client execution, navigation, forms, loading/error states, i18n, assets, and design tokens.
4. Model effect dependencies, cleanup, stale closures, suspense, transitions, hydration, and browser-only behavior.
5. Map UI semantics to React targets or Flutter/Swift/mobile targets through explicit component and navigation profiles.
6. Preserve accessibility roles, names, focus, keyboard, announcements, and responsive behavior.
7. Generate component, hook, integration, accessibility, visual, and end-to-end tests.
8. Verify critical journeys in supported browsers and rendering modes.

## Implementation Contract

- Adapter analysis uses the native compiler/type system where practical.
- Syntax-only fallbacks lower confidence and cannot support high-assurance claims alone.
- Unsupported or dynamic behavior remains in the semantic-loss register.
- Adapter output conforms to the shared Project, Semantic, Framework, and Behavior contracts.

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

- [ ] hook effect/cleanup/stale closure.
- [ ] context/state/cache ownership.
- [ ] SSR/hydration and server-client boundary.
- [ ] router/deep-link/forms.
- [ ] keyboard/focus/axe accessibility.
- [ ] React-to-Flutter component/navigation sample.

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
