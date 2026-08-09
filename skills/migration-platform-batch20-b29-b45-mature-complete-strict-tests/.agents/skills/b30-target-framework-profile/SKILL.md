---
name: b30-target-framework-profile
description: Design, implement, and certify a target framework profile covering architecture style, runtime, dependency injection, configuration, validation, security, persistence, transactions, messaging, cache, scheduling, observability, build, startup, and provider versions.
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


## Skill 1165: Target framework and provider profile

Make target generation deterministic and customer-reviewable by selecting an exact architecture and provider combination instead of relying on implicit framework defaults.

## Use this skill when

- A new target framework, architecture style, or provider combination is introduced.
- Generated targets differ unpredictably by environment or customer.
- A target profile must be certified for a deployment, database, broker, or industry constraint.

## Framework-specific risks and invariants

- Target defaults vary by version, especially serialization, DI lifetime, security, ORM, error handling, and shutdown.
- Third-party providers may not satisfy source transaction, message, cache, or scheduler contracts.
- Architecture style can change public APIs and code ownership.
- Too many optional provider combinations create an unmaintainable profile.

## Workflow

1. Inventory target skeletons, providers, lock files, security defaults, deployment profiles, and customer constraints.
2. Define exact runtime/build versions, architecture style, project layout, serializer, DI, configuration, validation, auth, ORM/database, transaction, broker, cache, scheduler, and observability.
3. Map every required FCM capability to target-native implementation, certified adapter, retained provider, compatibility component, or blocker.
4. Implement project scaffolding, provider registration, configuration, health, startup, shutdown, and operational hooks.
5. Add profile-specific contract tests and negative startup/configuration/provider tests.
6. Generate SBOM, license, vulnerability, and image/package provenance for added dependencies.
7. Measure compatibility budget, generated/manual ownership, and target maintainability.
8. Publish only after real build/startup and framework-gate evidence.

## Required repository outputs

- `framework-packs/<pack>/target-profile/profile.json`
- Exact dependency locks and image/toolchain digests
- Target scaffold/generator configuration
- Profile-specific contract and negative tests
- Provider SBOM/license/security/provenance evidence

## Verification

- Generate empty and representative targets and run real build/startup.
- Run configuration, DI lifetime, authentication, transaction, provider failure, health, and shutdown tests.
- Verify immutable dependency and image digests.
- Run maintainability and compatibility-budget checks.

## Stop and escalate when

- A source contract has no implementation, adapter, retained service, or explicit blocker.
- The profile uses mutable versions or undocumented defaults.
- Security, transaction, data, or message semantics are weakened to fit a provider.
- The provider combination has no maintenance owner.

## Definition of done

The target profile is exact, reproducible, builds and starts with real tools, implements declared FCM capabilities, has supply-chain evidence, and exposes explicit blockers and ownership.
