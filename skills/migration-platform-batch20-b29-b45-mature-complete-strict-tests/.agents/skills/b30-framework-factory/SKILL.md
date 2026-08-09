---
name: b30-framework-factory
description: Implement and certify a directional, version-specific framework migration or upgrade pack with runtime fingerprinting, framework contracts, target profiles, recipes, real builds, holdout corpora, and evidence. Use for Batch 30 pack creation or major expansion.
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


## Skill 1161: Framework migration factory orchestrator

Turn a requested source-framework/version and target-framework/version combination into a versioned, executable, evidence-backed framework pack that Codex can implement incrementally.

## Use this skill when

- A user asks to add a framework migration, modernization, or major-version upgrade path.
- An existing framework pack lacks a complete vertical slice, runtime evidence, or independent certification.
- Multiple Batch 30 skills must be coordinated into one production-shaped implementation.

## Framework-specific risks and invariants

- Framework behavior may come from configuration, auto-configuration, middleware order, proxies, generated code, or external providers rather than visible annotations alone.
- A declared source dependency does not prove that a capability is active at runtime.
- Similar framework APIs can have different lifecycle, transaction, security, validation, persistence, and error semantics.
- Version changes inside one framework can be as breaking as cross-framework migration.

## Workflow

1. Inspect existing framework adapters, FCM contracts, target generators, provider profiles, packs, and repository-native test commands; write `framework-packs/<pack>/certification/gap-inventory.md`.
2. Confirm accountable and maintenance owners, exact source/target/runtime/provider versions, pack mode, customer value, and the first vertical-slice scope.
3. Scaffold the pack when absent, then implement active source-framework fingerprinting before target generation.
4. Extract one complete framework-neutral contract set covering an entrypoint, DI, configuration, validation, security, persistence, transaction, and at least one integration or lifecycle boundary.
5. Select or implement an exact target profile; keep framework-specific facts outside core UIR and in FCM extensions or mappings.
6. Implement deterministic recipes and adapters, generate the target, and invoke real target build and startup tools.
7. Run development, negative, holdout, and representative-repository contract suites; fix systemic failures in fingerprint/FCM/recipe/generator layers.
8. Write version-lifecycle, maintenance, economics, and certification evidence, then invoke the gate skill rather than manually raising status.

## Required repository outputs

- `framework-packs/<pack-key>/pack.json` and `support-matrix.json`
- `framework-packs/<pack-key>/source-fingerprint/` and `contracts/`
- `framework-packs/<pack-key>/target-profile/profile.json`
- `framework-packs/<pack-key>/recipes/`, `adapters/`, and `compatibility/`
- `framework-packs/<pack-key>/corpus/{development,holdout,real-repository}/`
- `framework-packs/<pack-key>/certification/{evidence.json,certification.json}`

## Verification

- Run source build/runtime discovery and target build/startup using exact versions.
- Run applicable web, DI, configuration, validation, security, persistence, transaction, messaging/cache/scheduler, and lifecycle contract tests.
- Run `validate_framework_pack.py` and `run_framework_gate.py`.
- Verify a representative vertical slice starts and passes all declared P0 framework contracts.

## Stop and escalate when

- No owner or exact version tuple is approved.
- The only implementation strategy is annotation or API name substitution without runtime contracts.
- Green status requires weakening authentication, authorization, transactions, data constraints, provider semantics, or tests.
- Independent holdout or representative-repository evidence is unavailable for a certification claim.

## Definition of done

The pack contains executable source fingerprinting, versioned FCM contracts, an exact target profile, deterministic mappings, real build/startup evidence, independent corpora, explicit limitations, and only the strongest status justified by the gate.
