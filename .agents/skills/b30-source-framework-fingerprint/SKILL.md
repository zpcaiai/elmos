---
name: b30-source-framework-fingerprint
description: Implement static and runtime fingerprinting for a source framework, including dependencies, active configuration, routes, components, middleware, security, persistence, transactions, messaging, cache, schedulers, generated code, and provider usage. Use before contract extraction.
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


## Skill 1164: Source framework runtime fingerprinting

Discover what a source application actually uses at build and runtime, with confidence and provenance, so target generation is based on active behavior rather than declared dependencies or annotation guesses.

## Use this skill when

- A new source framework or version is added.
- Static discovery misses auto-configuration, runtime registration, generated code, or external configuration.
- An existing pack has false positives, false negatives, or unexplained target gaps.

## Framework-specific risks and invariants

- Declared packages, starters, modules, or extensions may be unused.
- Profiles, environment variables, plugins, reflection, and build-time augmentation can alter active behavior.
- Test-only components must not be mistaken for production components.
- Instrumentation must not mutate source behavior or leak secrets/source beyond policy.

## Workflow

1. Inspect build files, lock files, annotations/decorators, configuration, generated sources, plugins, runtime modules, and current discovery code.
2. Define a versioned fingerprint schema with category, source reference, activation conditions, profile/environment, provider, confidence, and evidence.
3. Implement static discovery for source and build metadata.
4. Implement safe runtime or build-time introspection for routes, components, providers, middleware, security, data, transactions, jobs, and lifecycle where needed.
5. Reconcile findings into active, conditional, declared-only, generated, test-only, unknown, and conflicting facts.
6. Map active facts into FCM extraction inputs and explicit obligations.
7. Add fixtures for profiles, conditional components, generated code, custom plugins, and unused dependencies.
8. Measure critical discovery coverage on physically separate holdout and representative repositories.

## Required repository outputs

- `engines/<framework>-adapter/fingerprint/` implementation
- `packages/framework-fingerprint-contracts/` schema/bindings
- `framework-packs/<pack>/source-fingerprint/{manifest.json,evidence.json}`
- Static/runtime reconciliation fixtures
- Coverage and unknown-capability report

## Verification

- Run the source application or framework-native inspection tool where safe.
- Verify production, conditional, generated, and test-only facts are distinguished.
- Verify secret and source-egress policies during runtime introspection.
- Run holdout repositories and compute critical coverage.

## Stop and escalate when

- Only dependency-name detection exists for a capability claimed active.
- Runtime discovery requires unsafe production access or forbidden data egress.
- Conditional activation would be flattened into unconditional behavior.
- Critical unknown capabilities remain for certification.

## Definition of done

The adapter emits a sanitized, versioned, confidence-rated fingerprint that reconciles static and runtime facts, drives FCM extraction, and achieves the declared holdout coverage.
