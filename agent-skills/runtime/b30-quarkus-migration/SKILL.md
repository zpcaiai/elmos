---
name: b30-quarkus-migration
description: "Implement or certify a Quarkus source or target framework pack, including build-time augmentation, Arc CDI, REST, configuration, Panache/Hibernate ORM, transactions, security, messaging, dev services, native-image constraints, and operational behavior."
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


## Skill 1168: Quarkus migration and target profile

Support exact-version migration into or out of Quarkus without losing build-time, CDI, REST, persistence, transaction, security, messaging, native-image, and lifecycle semantics.

## Use this skill when

- Quarkus is the selected source or target framework.
- A Spring/Jakarta service is moving to Quarkus.
- A Quarkus pack needs another exact extension/provider or native-image certification.

## Framework-specific risks and invariants

- Quarkus build-time augmentation and extension discovery cannot be treated as ordinary runtime reflection.
- Arc CDI, REST stacks, config phases, Panache, Dev Services, and native behavior require explicit profiles.
- JVM-mode success does not prove native-image compatibility.
- Extension/provider combinations materially affect startup, security, persistence, transaction, and messaging.

## Workflow

1. Lock Quarkus, Java, build plugin, extensions, REST stack, ORM/database, security, messaging, scheduler, test, and native toolchain versions.
2. Fingerprint extensions, build items, CDI beans/interceptors/scopes, routes, config phases, Panache/ORM, transactions, security, messaging, jobs, Dev Services, and native registrations.
3. Extract or consume FCM contracts; keep build-time facts in a namespaced Quarkus extension.
4. Implement source/target mappings and a target profile for JVM mode first; classify native-image support independently.
5. Generate extension registration, config, health, observability, tests, and source maps for a complete vertical slice.
6. Run real Quarkus build/startup plus web, DI, security, persistence, transaction, messaging, health, and shutdown contracts.
7. For native-certified scope, run real native build/runtime and validate reflection, proxies, resources, serialization, and providers.
8. Run holdout cases for custom extensions, interceptors, Panache styles, reactive variants, and native restrictions.

## Required repository outputs

- `framework-packs/<source>-to-quarkus/` or reverse pack
- Extension/build-time fingerprint and version matrix
- JVM/native support matrix
- Quarkus adapters, recipes, target profile, and tests
- Native reflection/proxy/resource config where proven
- Build/startup/holdout evidence

## Verification

- Run exact Quarkus JVM build/startup and declared contract suites.
- Run native build/runtime only for native-certified capabilities.
- Verify build-time facts are deterministic and source-traceable.
- Run representative repositories and the framework gate.

## Stop and escalate when

- Build-time behavior is approximated as runtime reflection.
- Native support is claimed from JVM-only evidence.
- Required extension/provider versions are mutable or unsupported.
- Reactive and imperative semantics are conflated.

## Definition of done

The Quarkus pack has exact extensions/providers, build-time and runtime contracts, real JVM evidence, native evidence only where proven, holdout coverage, and explicit restricted capabilities.
