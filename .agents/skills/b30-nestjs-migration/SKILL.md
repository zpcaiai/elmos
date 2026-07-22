---
name: b30-nestjs-migration
description: Implement or certify a NestJS source or target framework pack, covering modules, providers and scopes, controllers, pipes, guards, interceptors, filters, decorators, configuration, validation, authentication/authorization, persistence providers, microservices, queues, schedulers, and lifecycle hooks.
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


## Skill 1177: NestJS framework migration

Migrate into or out of NestJS while preserving its module/DI graph, request pipeline, metadata, security, persistence, microservice, queue, scheduler, and lifecycle behavior.

## Use this skill when

- NestJS is a source or target.
- A Node/TypeScript service needs migration to Java, C#, Python, or another Node framework.
- A current Nest pack lacks module graph, guard/interceptor, provider, or transport evidence.

## Framework-specific risks and invariants

- Modules, dynamic modules, providers, scopes, tokens, decorators, and metadata form a runtime graph.
- Pipes, guards, interceptors, filters, middleware, and decorators have order and short-circuit semantics.
- Persistence may use TypeORM, Prisma, Mongoose, or custom providers with different transactions.
- Microservice transports, queues, schedulers, and lifecycle hooks are provider-specific.

## Workflow

1. Lock Node, TypeScript, NestJS, metadata, validation, security, persistence, transport, queue, scheduler, and test versions.
2. Fingerprint module/dynamic-module graph, providers/tokens/scopes, controllers/routes, ordered pipeline components, config, validation, auth, persistence, microservices, queues, schedulers, and lifecycle hooks.
3. Extract FCM plus namespaced Nest module/metadata facts.
4. Select a target profile and implement a complete controller-service-persistence or message-worker slice.
5. Generate provider registration, pipeline order, security, validation, persistence/transaction, integrations, tests, observability, and source maps.
6. Run real source and target build/startup plus HTTP/security/pipeline/data/message/scheduler/lifecycle tests.
7. Run holdout cases for dynamic modules, custom tokens, request scope, custom decorators, multiple transports, and provider-specific transactions.
8. Publish support matrix, maintenance plan, and migration guide.

## Required repository outputs

- `framework-packs/nestjs-to-<target>/` or reverse pack
- Module/provider/pipeline runtime fingerprint
- Nest FCM extensions and target mappings
- Persistence/transport provider profiles
- Real build/startup and contract corpus
- Holdout/certification evidence

## Verification

- Run real TypeScript/Nest build and startup.
- Run module/DI scope, route, pipeline, validation, security, persistence/transaction, transport, queue/scheduler, and shutdown tests.
- Run target runtime and compare P0 contracts.
- Run holdout and the gate.

## Stop and escalate when

- Dynamic module/provider metadata is not captured.
- Pipeline components are reordered or merged without tests.
- Request-scoped providers become singletons.
- Persistence or transport semantics are assumed from API similarity.

## Definition of done

The NestJS pack captures module/DI and request/integration pipelines, migrates a real slice, passes source-target and holdout tests, and has explicit provider/version and dynamic-metadata boundaries.
