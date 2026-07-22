---
name: b30-aspnet-to-spring
description: "Implement and certify the directional ASP.NET Core or supported ASP.NET source to Spring Boot target framework pack, preserving routes, model binding, middleware, DI lifetimes, Options, validation, authentication/authorization, EF Core, transactions, hosted services, messaging, cache, and errors."
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


## Skill 1171: ASP.NET to Spring Boot reverse migration

Build the reverse framework path independently from Spring-to-ASP.NET by extracting ASP.NET runtime contracts and generating a versioned Spring Boot target implementation.

## Use this skill when

- A customer requests ASP.NET Core to Spring Boot migration.
- Batch 29 C# to Java support exists and needs framework-level integration.
- An existing reverse pack lacks runtime, security, persistence, hosted-service, or holdout evidence.

## Framework-specific risks and invariants

- ASP.NET middleware order, endpoint routing, binding, filters, and Problem Details cannot be mapped by attribute names alone.
- DI lifetimes, keyed services, Options snapshot/monitor, hosted services, and cancellation differ from Spring.
- Authentication schemes and policy/resource authorization do not map directly to roles or annotations.
- EF Core tracking, LINQ translation, concurrency tokens, migrations, and providers differ from JPA/Hibernate.

## Workflow

1. Lock source ASP.NET/.NET and target Java/Spring versions plus serializer, ORM/database, auth, broker, cache, scheduler, and test providers.
2. Fingerprint controllers/minimal APIs, middleware, filters, DI, Options/configuration, validation, authentication schemes, authorization policies/handlers, EF Core, transactions, hosted services, messaging, cache, and jobs.
3. Extract versioned FCM contracts with source trace, runtime facts, conditions, order, and provider versions.
4. Select a Spring target profile and implement a complete protected Controller-Service-Repository or Worker vertical slice.
5. Generate Java/Spring code, config, security chains/policies, JPA mappings, transactions, workers, tests, providers, and source maps.
6. Run real source and target builds/startup plus HTTP, security, data, transaction, background-service, integration, and error contracts.
7. Run holdout cases for minimal APIs, multiple schemes, resource authorization, keyed DI, EF provider queries, cancellation, and hosted services.
8. Publish support matrix, migration guide, coexistence path, and gate evidence.

## Required repository outputs

- `framework-packs/aspnet-core-to-spring-boot/`
- ASP.NET runtime fingerprint and FCM contracts
- Spring target profile and generators
- Security/EF/hosted-service recipes and adapters
- Source-target contract corpus and holdout evidence
- Certification record

## Verification

- Run real `dotnet` source and Java/Spring target builds/startup.
- Run endpoint/binding/error, DI/config, auth, persistence/transaction, hosted-service, message/cache/job, and shutdown tests.
- Verify source maps and absence of permissive type/security fallbacks.
- Run holdout and the Batch 30 gate.

## Stop and escalate when

- The implementation reuses forward-direction assumptions instead of independent reverse contracts.
- Authorization policies are flattened into coarse roles.
- EF/LINQ behavior lacks database execution evidence.
- Hosted-service, cancellation, or middleware behavior would be silently lost.

## Definition of done

The directed ASP.NET-to-Spring pack independently fingerprints source behavior, generates a real Spring target, passes P0 and holdout contracts, and has zero critical security/data/transaction unknowns.
