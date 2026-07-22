---
name: b30-fastapi-migration
description: "Implement or certify a FastAPI source or target framework pack, covering route and dependency graphs, Pydantic schemas, async behavior, validation, middleware, lifespan, security dependencies, OpenAPI, exception handling, background tasks, and provider integrations."
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


## Skill 1172: FastAPI framework migration

Support exact-version migration into or out of FastAPI while preserving ASGI request handling, dependency injection, Pydantic validation/serialization, async/lifespan, security, errors, background tasks, streaming, and OpenAPI contracts.

## Use this skill when

- FastAPI is a source or target framework in a language route.
- A FastAPI application needs framework replacement or version modernization.
- Pydantic, dependency, or async behavior causes unresolved differences.

## Framework-specific risks and invariants

- Dependency functions form a runtime graph with scopes, caching, yield cleanup, security, and async behavior.
- Pydantic version/config changes affect coercion, aliases, defaults, serialization, discriminators, and OpenAPI.
- ASGI middleware, lifespan, exception handlers, background tasks, streaming, and WebSockets have order/resource contracts.
- Python decorators, dynamic typing, monkey patching, and runtime registration can hide behavior.

## Workflow

1. Lock Python, FastAPI, Starlette, Pydantic, ASGI server, security, persistence, task, and test versions.
2. Fingerprint routers, operation IDs, dependency/security graphs, middleware order, lifespan, errors, response models, background tasks, streaming/WebSockets where in scope, OpenAPI customizations, and providers.
3. Extract FCM web/config/validation/security/lifecycle/error contracts plus explicit Python dynamic obligations.
4. Select a target profile or implement FastAPI target generation with exact Pydantic and runtime settings.
5. Generate one complete endpoint-service-persistence or endpoint-external-call slice with tests and source maps.
6. Run real source and target startup, OpenAPI comparison, request/response/error/security/dependency/lifespan/background-task contracts.
7. Run async cancellation, yield cleanup, streaming, and provider failure cases.
8. Run holdout cases for nested dependencies, aliases, unions/discriminators, custom OpenAPI, and dynamic registration.

## Required repository outputs

- `framework-packs/fastapi-to-<target>/` or reverse pack
- FastAPI route/dependency/security graph
- Pydantic validation/serialization contracts
- ASGI middleware/lifespan/error contracts
- Target recipes/adapters and OpenAPI evidence
- Holdout and certification record

## Verification

- Run real FastAPI startup and target build/startup.
- Compare OpenAPI and HTTP, dependency cleanup, validation, serialization, security, task, streaming, and lifecycle behavior.
- Run async cancellation and error cases.
- Run holdout repositories and the gate.

## Stop and escalate when

- Pydantic coercion or serialization differences are ignored.
- Yield cleanup or security scopes cannot be represented.
- Dynamic route/monkey-patch behavior is active but undiscovered.
- Async behavior is made synchronous without approved contract change.

## Definition of done

The FastAPI pack captures dependency, Pydantic, ASGI, security, error, and lifecycle behavior, migrates a real slice, passes runtime/OpenAPI/holdout tests, and explicitly restricts unsupported dynamic patterns.
