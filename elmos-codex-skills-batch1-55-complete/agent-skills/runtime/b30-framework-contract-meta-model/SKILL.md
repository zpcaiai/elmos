---
name: b30-framework-contract-meta-model
description: "Design or extend the framework-neutral Framework Contract Model used to represent web, dependency injection, configuration, validation, security, persistence, transactions, messaging, cache, scheduling, and lifecycle behavior. Use before framework-specific code generation."
---

## Operating mode

Work in the repository. Inspect existing Batch 20-29 modules, contracts, build commands, framework packs, and tests before editing. Implement the smallest production-shaped vertical slice that satisfies this skill; do not stop at a design document when code, manifests, and executable tests can be added.

Read these shared contracts first:

- `../../../docs/batch30/IMPLEMENTATION_CONTRACT.md`
- `../../../docs/batch30/QUALITY_GATES.md`
- `../../../docs/batch30/REPOSITORY_LAYOUT.md`
- `../../../docs/batch30/VERSION_POLICY.md`

Use the supplied helpers where applicable:

- `python3 scripts/batch30/scaffold_framework_pack.py ...`
- `python3 scripts/batch30/validate_framework_pack.py ...`
- `python3 scripts/batch30/run_framework_gate.py ...`

## Global constraints

- Treat every framework migration pack as directional and version-specific. Reverse migration and version upgrade are separate packs.
- Extract runtime behavior into the framework-neutral Framework Contract Model before generating target code. Do not implement annotation-name substitution as the migration architecture.
- Invoke real source and target build/runtime tools. A generated project that only parses is not evidence of support.
- Preserve authentication, authorization, transaction, persistence, message delivery, configuration precedence, validation, lifecycle, and error contracts.
- Keep development, holdout, and representative-repository corpora physically separate. Do not author rules from holdout cases.
- Prefer deterministic mappings and certified adapters. Model-generated output is a candidate and must pass the same build, contract, behavior, security, and test-integrity gates.
- Record unsupported, conditional, and unknown behavior explicitly. Never hide it with TODOs, permissive stubs, broad exception swallowing, disabled security, or weakened tests.
- Record exact framework/runtime/provider versions, source and target commits, recipe digest, model/prompt versions, toolchain digests, and evidence references.
- Fix repeated failures in the fingerprint, contract model, recipe, adapter, or generator instead of patching many generated files.
- Run the narrowest relevant tests first, then the independent holdout suite and framework certification gate before making release claims.


## Skill 1162: Framework Contract meta-model

Implement a versioned Framework Contract Model (FCM) that separates source runtime behavior from target implementation, allowing multiple frameworks to share contracts without contaminating core UIR.

## Use this skill when

- A new framework capability cannot be represented by current contracts.
- A source annotation or target API has leaked into core UIR.
- Two packs need a common neutral contract for equivalent behavior.

## Framework-specific risks and invariants

- Ordering, conditions, defaults, lifecycle, provider behavior, and error timing are part of framework semantics.
- Framework defaults differ by version and must be materialized rather than assumed.
- Namespaced extensions are useful but must not become mandatory core semantics for unrelated frameworks.
- Breaking FCM changes can invalidate stored artifacts, recipes, and long-running workflows.

## Workflow

1. Inventory current FCM schemas, stable IDs, source extensions, target mappings, stored artifacts, and compatibility rules.
2. Define the smallest neutral concepts and invariants needed; place source-specific facts only in namespaced extensions.
3. Add stable IDs, source trace, confidence, applicability conditions, ordering, version, and obligation fields.
4. Implement repository-standard IDL or JSON Schema plus generated bindings for supported implementation languages.
5. Implement conformance validation, deterministic serialization, reference integrity, unknown-field compatibility, and schema migration.
6. Update at least one source adapter and one target consumer; use two unrelated frameworks when feasible to prove neutrality.
7. Add positive, negative, round-trip, backward-compatibility, and forward-compatibility fixtures.
8. Document affected packs and provide migration tooling before changing certified stored contracts.

## Required repository outputs

- `packages/framework-contracts/` versioned schemas and generated bindings
- `engines/framework-contract-core/` validators, canonicalization, and migrations
- `tests/framework-contracts/` conformance and compatibility fixtures
- FCM changelog and affected-pack migration records
- Updated adapter/generator code demonstrating real consumption

## Verification

- Validate all schemas and generated bindings.
- Run deterministic serialization and backward/forward compatibility tests.
- Run source-trace and cross-contract reference checks.
- Demonstrate real adapter and generator use without direct source/target framework coupling.

## Stop and escalate when

- A proposed core field merely copies a source annotation or target class name without neutral meaning.
- A breaking schema change lacks migration/version strategy.
- Ordering, default, condition, lifecycle, or provider behavior remains implicit.
- Certified packs would silently change behavior.

## Definition of done

The new FCM capability is neutral, versioned, traceable, deterministic, compatible or migratable, covered by conformance tests, and proven through executable source and target integrations.
