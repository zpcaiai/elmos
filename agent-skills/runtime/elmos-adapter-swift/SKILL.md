---
name: elmos-adapter-swift
description: "Implement Swift analysis and conversion for optionals, protocols, generics, value semantics, actors, async, SwiftUI/UIKit, and Objective-C interoperability."
version: 1.0.0
skill_id: ELMOS-POLY-060
layer: technology-adapter
risk: critical
readiness: not-run
dependencies:
  - "elmos-build-toolchain-discovery"
triggers:
  - "Use when implementing or executing `elmos-adapter-swift`."
  - "Use when the current DAG node requires the technology-adapter capability."
  - "Use when `swift` is a source, target, interoperability, or modernization technology."
  - "Use when files or build roots matching .swift, Package.swift are detected."
outputs:
  - "adapters/swift/adapter-manifest.json"
  - "adapters/swift/parser-profile.yaml"
  - "adapters/swift/semantic-mapping.yaml"
  - "adapters/swift/verification-profile.yaml"
---

# Adapter Swift

## Objective

Implement Swift analysis and conversion for optionals, protocols, generics, value semantics, actors, async, SwiftUI/UIKit, and Objective-C interoperability.

This Skill is an **implementation and execution contract**. It tells Codex, Claude Code, or another authorized coding agent what code, schemas, tests, policies, and evidence must exist. The presence of this file is not proof that the capability has been implemented.

## When to use

- Use when implementing or executing `elmos-adapter-swift`.
- Use when the current DAG node requires the technology-adapter capability.
- Use when `swift` is a source, target, interoperability, or modernization technology.
- Use when files or build roots matching .swift, Package.swift are detected.

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
- Technology registry entry `swift` and the detected native toolchain profile.

## Outputs

- `adapters/swift/adapter-manifest.json`
- `adapters/swift/parser-profile.yaml`
- `adapters/swift/semantic-mapping.yaml`
- `adapters/swift/verification-profile.yaml`

## Technology profile

| Field | Value |
|---|---|
| Registry ID | `swift` |
| Display name | Swift |
| Kind | language |
| File/build markers | `.swift`, `Package.swift` |
| Build systems | SwiftPM, Xcode, xcodebuild |
| Preferred analyzers | SwiftSyntax, SourceKit-LSP, Swift compiler AST |
| Framework coverage | SwiftUI, UIKit, Vapor, Combine, Core Data |
| Native verification | `swift test`, `xcodebuild test`, `swiftlint`, `XCTest` |

### Semantic risk register

- value versus reference semantics.
- optional and error handling.
- protocol existentials and opaque types.
- actors and Sendable.
- SwiftUI identity/state/lifecycle.
- Objective-C interoperability.
- compiler/source compatibility.

## Guardrails

- Do not modify files outside the authorized worktree.
- Do not expose credentials, tokens, private keys, customer data, or proprietary source to unapproved tools or models.
- Do not disable tests, weaken assertions, suppress scanner errors, or mark missing evidence as passed.
- Do not claim production readiness from static package generation.
- Preserve unresolved assumptions and blockers in the completion report.

## Workflow

1. Detect Swift version, SwiftPM/Xcode targets, build configurations, package graph, macros/plugins, generated sources, and supported OS versions.
2. Use SwiftSyntax and SourceKit/compiler semantic information to resolve declarations, types, protocols, generics, concurrency, and source locations.
3. Lower structs/classes/enums, protocols, extensions, optionals, throws/Result, closures, ownership, copy-on-write, and access control into Semantic IR.
4. Represent async/await, actors, tasks, cancellation, isolation, Sendable, and main-actor requirements.
5. Lower SwiftUI state/environment/navigation/view identity and UIKit lifecycle/delegation into Framework IR.
6. Preserve @objc/dynamic selectors, bridging, Core Foundation, and binary framework constraints.
7. Map to Flutter or other targets through behavior and platform-service contracts.
8. Verify with swift test/xcodebuild/XCTest, concurrency checks, UI tests, and ABI/API checks where required.

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

- [ ] value/reference and copy-on-write.
- [ ] optionals/throws/Result.
- [ ] actor isolation/Sendable/cancellation.
- [ ] SwiftUI identity/state/navigation.
- [ ] UIKit and Objective-C interop.
- [ ] package/Xcode platform matrix.

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
