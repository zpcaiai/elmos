---
name: b30-micronaut-migration
description: Implement or certify a Micronaut source or target framework pack, covering compile-time dependency injection and AOP, HTTP, configuration, validation, data access, transactions, security, messaging, scheduling, native-image behavior, and version-specific providers.
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


## Skill 1169: Micronaut migration and target profile

Support migration into or out of Micronaut while preserving compile-time DI/AOP, request, configuration, validation, security, persistence, transaction, messaging, scheduler, and lifecycle contracts.

## Use this skill when

- Micronaut is the source or target framework.
- A Spring/Jakarta application is moving to Micronaut.
- A Micronaut pack needs another version, language, provider, or native profile.

## Framework-specific risks and invariants

- Micronaut uses compile-time metadata and generated bean definitions; source annotations alone are insufficient.
- AOP, scopes, conditions, config, HTTP binding, and validation depend on generated metadata.
- Micronaut Data supports multiple styles/providers with different query and transaction behavior.
- Native-image and reflection constraints need independent execution evidence.

## Workflow

1. Lock Micronaut, source language, annotation processors, HTTP stack, data provider, security, messaging, scheduler, tests, and native toolchain.
2. Fingerprint generated bean metadata, AOP interceptors, scopes, conditions, routes, configuration, validation, security, persistence, transactions, integrations, jobs, health, and lifecycle.
3. Extract FCM and namespaced compile-time metadata facts.
4. Implement source/target adapters and recipes including annotation-processor and generated-source ordering.
5. Generate a complete target vertical slice with build config, DI registrations, providers, tests, observability, and source maps.
6. Run real build/startup plus web, AOP, security, data, transaction, message, scheduler, and shutdown tests.
7. Run native-image tests only for explicitly declared native scope.
8. Add holdout cases for custom AOP, conditions, query generation, multiple source languages, and native restrictions.

## Required repository outputs

- `framework-packs/<source>-to-micronaut/` or reverse pack
- Compile-time metadata and generated-source fingerprint
- Micronaut provider/version profile
- DI/AOP/HTTP/Data/Security recipes and adapters
- JVM/native evidence and holdout corpus

## Verification

- Run exact Micronaut build and inspect generated metadata.
- Run target startup and all declared DI/AOP/web/security/data/transaction/integration/lifecycle contracts.
- Verify annotation-processing stages are not skipped.
- Run holdout and the framework gate.

## Stop and escalate when

- Compile-time metadata cannot be captured or generated deterministically.
- AOP or conditional bean behavior would be silently dropped.
- Data/query semantics are assumed without database evidence.
- Native support is claimed without native execution.

## Definition of done

The Micronaut pack captures compile-time and runtime behavior, generates and starts a real application, passes declared contracts and holdout cases, and clearly separates JVM and native support.
