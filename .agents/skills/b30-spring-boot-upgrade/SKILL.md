---
name: b30-spring-boot-upgrade
description: Implement and certify a Spring Boot major or minor version upgrade pack, including Java/runtime changes, Jakarta namespace transitions, configuration properties, auto-configuration, Spring Security, Hibernate/JPA, Actuator, build plugins, tests, and behavior evidence.
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


## Skill 1166: Spring Boot version upgrade and modernization

Upgrade a Spring Boot application between exact source and target versions while preserving web, DI, configuration, validation, security, persistence, transaction, integration, Actuator, lifecycle, and test contracts.

## Use this skill when

- A customer needs Spring Boot, Spring Framework, Java, Jakarta, Hibernate, or Spring Security modernization without changing framework family.
- A Spring pack must support another exact source-to-target version edge.
- Automated upgrade recipes need real build/startup and independent holdout certification.

## Framework-specific risks and invariants

- Jakarta namespace transitions affect source, generated code, dependencies, XML, serialization, and containers.
- Auto-configuration and property names, binding, precedence, and defaults can change.
- Spring Security DSL, filter ordering, encoders, CSRF/CORS/session defaults, and method security can change.
- Hibernate/JPA provider behavior, SQL generation, lazy loading, dialects, schema validation, and migrations can change.
- Build plugins, AOT/native support, Actuator endpoints, and test slices can change.

## Workflow

1. Create or inspect an exact pack such as `spring-boot-<source>-to-<target>` and lock Java, Maven/Gradle, Spring, provider, plugin, test, and image versions.
2. Fingerprint active starters, auto-configurations, properties, profiles, conditional beans, security chains, JPA mappings, transactions, messaging, cache, scheduler, Actuator, generated code, and tests.
3. Build an applicable-change inventory from official migration notes plus repository/runtime evidence; convert every applicable change into FCM, build, or manual obligations.
4. Apply deterministic namespace, dependency, configuration, API, DSL, and test recipes in dependency-aware order.
5. Fix repeated issues in recipes/generators; preserve customer-owned extensions and target drift.
6. Run source baseline, upgraded build, startup, endpoints, security, persistence, transaction, integration, health, and shutdown tests.
7. Run independent holdout projects covering deprecated APIs, custom auto-configuration, multi-module builds, profiles, and provider differences.
8. Publish upgrade/rollback guidance, unsupported patterns, lifecycle evidence, and the framework gate result.

## Required repository outputs

- `framework-packs/spring-boot-<source>-to-<target>/` complete pack
- Applicable version-change and dependency graph manifest
- Ordered upgrade recipes and configuration-property mappings
- Security/JPA/transaction/Actuator evidence
- Customer upgrade, coexistence, and rollback guide
- Holdout and certification artifacts

## Verification

- Run exact source and target Maven/Gradle builds and application startup.
- Run endpoint, configuration, security, persistence, transaction, integration, Actuator, and shutdown tests.
- Run holdout repositories not used to author recipes.
- Run pack validation and the Batch 30 gate.

## Stop and escalate when

- Exact Spring/Java/provider versions are unknown.
- Security defaults or transaction/data behavior would change without explicit tests.
- Green status requires disabling validation, schema checks, tests, or security.
- Custom auto-configuration or generated code is active but unaccounted for.

## Definition of done

The exact Spring upgrade edge has active-runtime fingerprinting, deterministic recipes, real build/startup evidence, P0 contract and holdout passes, explicit rollback guidance, and no critical unknowns.
