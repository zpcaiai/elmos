# Batch 98 — Executable Skill Contract and Registry Pack

## Purpose

Turns governed Skills into signed executable contracts. Markdown remains human-readable guidance; typed contracts enforce behavior.

System objective: compile Markdown Skills into signed executable contracts with schemas, permissions, rollback, tests, registry, search, dependency resolution and compatibility governance.

## Inventory

- Skills: **16**
- Stable local IDs: **B98-S01–B98-S16**
- Global IDs: intentionally unassigned to avoid collision with the user's existing Batch 81–96 package.

| ID | Skill | Title | Purpose |
|---|---|---|---|
| B98-S01 | `b98-executable-skill-contract-schema` | Executable Skill Contract Schema | Define the authoritative versioned contract that makes a Skill executable rather than prose-only. |
| B98-S02 | `b98-skill-markdown-contract-compiler` | Skill Markdown Contract Compiler | Compile approved Skill Markdown and frontmatter into deterministic executable contracts with source maps. |
| B98-S03 | `b98-input-output-schema-binder` | Input and Output Schema Binder | Bind every input and output to exact schemas, content types, ownership and retention rules. |
| B98-S04 | `b98-precondition-guard-compiler` | Precondition and Guard Compiler | Compile preconditions, stop conditions and approval requirements into fail-closed executable guards. |
| B98-S05 | `b98-permission-capability-declaration` | Permission and Capability Declaration | Declare least-privilege process, filesystem, network, repository, secret, cloud and signing capabilities for each Skill. |
| B98-S06 | `b98-execution-step-compiler` | Execution Step Compiler | Compile workflows into typed, idempotent and resumable execution steps with explicit inputs, outputs and effects. |
| B98-S07 | `b98-rollback-compensation-compiler` | Rollback and Compensation Compiler | Compile reversible actions, compensations and irreversible decision gates into runtime-ready plans. |
| B98-S08 | `b98-test-evidence-contract-compiler` | Test and Evidence Contract Compiler | Compile required tests and evidence into machine-enforced obligations bound to exact states and scopes. |
| B98-S09 | `b98-deterministic-variable-resolver` | Deterministic Variable Resolver | Resolve parameters, defaults, environment references and secrets without hidden nondeterminism or plaintext exposure. |
| B98-S10 | `b98-contract-signing-provenance` | Contract Signing and Provenance | Sign executable contracts and bind them to source Skill, compiler, policy and dependency snapshots. |
| B98-S11 | `b98-skill-registry-service` | Skill Registry Service | Implement tenant-aware storage, retrieval, lifecycle and immutable versioning for executable Skill contracts. |
| B98-S12 | `b98-capability-search-ranking` | Capability Search and Ranking | Rank candidate Skills by capability fit, evidence, compatibility, cost, risk and historical outcomes without loading the full estate. |
| B98-S13 | `b98-dependency-closure-resolver` | Dependency Closure Resolver | Resolve the minimal compatible dependency closure for a selected Skill or route pack. |
| B98-S14 | `b98-skill-conflict-arbitrator` | Skill Conflict Arbitrator | Arbitrate overlapping write sets, contradictory policies and competing implementations before execution. |
| B98-S15 | `b98-contract-compatibility-deprecation` | Contract Compatibility and Deprecation | Validate contract schema evolution, behavior compatibility, replacement paths and deprecation windows. |
| B98-S16 | `b98-executable-contract-certification-gate` | Executable Contract Certification Gate | Certify executable contracts only when compilation, guards, permissions, dependencies, rollback, tests, evidence and signatures are complete. |

## Batch completion gate

The Batch is not complete merely because these Markdown files validate. Completion requires implementation in the target ELMOS repository, real integration tests, failure-path evidence, exact scope binding and the final Batch certification Skill result.
