---
name: elmos-adapter-cpp
description: "Implement C++ analysis and modernization support using compiler-grade AST evidence, explicit ABI/ownership modeling, and safety validation."
version: 1.0.0
skill_id: ELMOS-POLY-055
layer: technology-adapter
risk: critical
readiness: not-run
dependencies:
  - "elmos-build-toolchain-discovery"
triggers:
  - "Use when implementing or executing `elmos-adapter-cpp`."
  - "Use when the current DAG node requires the technology-adapter capability."
  - "Use when `cpp` is a source, target, interoperability, or modernization technology."
  - "Use when files or build roots matching .cc, .cpp, .cxx, .h are detected."
outputs:
  - "adapters/cpp/adapter-manifest.json"
  - "adapters/cpp/parser-profile.yaml"
  - "adapters/cpp/semantic-mapping.yaml"
  - "adapters/cpp/verification-profile.yaml"
---

# Adapter Cpp

## Objective

Implement C++ analysis and modernization support using compiler-grade AST evidence, explicit ABI/ownership modeling, and safety validation.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-adapter-cpp`.
- Use when the current DAG node requires the technology-adapter capability.
- Use when `cpp` is a source, target, interoperability, or modernization technology.
- Use when files or build roots matching .cc, .cpp, .cxx, .h are detected.

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
- Technology registry entry `cpp` and the detected native toolchain profile.

## Outputs

- `adapters/cpp/adapter-manifest.json`
- `adapters/cpp/parser-profile.yaml`
- `adapters/cpp/semantic-mapping.yaml`
- `adapters/cpp/verification-profile.yaml`

## Technology profile

| Field | Value |
|---|---|
| Registry ID | `cpp` |
| Display name | C++ |
| Kind | language |
| File/build markers | `.cc`, `.cpp`, `.cxx`, `.h`, `.hpp`, `.hxx` |
| Build systems | CMake, Meson, Bazel, Make |
| Preferred analyzers | Clang AST, Clang LibTooling, clangd, tree-sitter-cpp |
| Framework coverage | STL, Boost, Qt, gRPC C++, Poco |
| Native verification | `cmake --build`, `ctest`, `clang-tidy`, `AddressSanitizer`, `UndefinedBehaviorSanitizer` |

### Semantic risk register

- preprocessor and build configuration variability.
- templates and overload resolution.
- manual ownership and undefined behavior.
- ABI and binary compatibility.
- multiple inheritance and RTTI.
- RAII, exceptions, and move semantics.
- native concurrency and platform APIs.

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Detect compiler, language standard, target triples, CMake/Meson/Bazel/Make graph, compile_commands, macros, features, and linked binaries.
2. Use Clang AST/LibTooling with actual compile commands; treat tree-sitter as discovery only.
3. Lower types, templates, concepts, inheritance, overloads, lambdas, exceptions, RAII, smart/raw pointers, moves, and resource ownership into Semantic IR.
4. Model preprocessor variants, conditional compilation, platform APIs, ABI, name mangling, layout, and binary boundaries.
5. Identify undefined behavior, aliasing, lifetime, data-race, macro, inline assembly, and opaque library risks.
6. Lower Qt/gRPC/Boost and application lifecycle patterns into Framework IR where supported.
7. Prefer strangler/FFI boundaries over blind full rewrites when ABI or hardware dependencies dominate.
8. Verify with native builds, ctest, clang-tidy, sanitizers, ABI tools, fuzzing, and representative platforms.

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

- [ ] compile-command and macro matrix.
- [ ] templates/overload/multiple inheritance.
- [ ] RAII/move/exception lifetime.
- [ ] ABI/layout compatibility.
- [ ] sanitizer-seeded defects.
- [ ] Qt signal/slot or native callback fixture.

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
