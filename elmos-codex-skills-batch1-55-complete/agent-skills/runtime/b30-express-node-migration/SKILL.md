---
name: b30-express-node-migration
description: "Implement or certify Express and general Node.js service migration, including route and middleware ordering, request/response mutation, async error propagation, sessions, body parsing, templates, app locals, module loading, process lifecycle, observability, and provider integrations."
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


## Skill 1178: Express and Node.js service migration

Discover and migrate convention-heavy Express/Node applications without losing dynamic route order, middleware, context, error, session, stream, module, and process lifecycle behavior.

## Use this skill when

- Express or a convention-based Node service is the source or target.
- An unstructured Node service must move to NestJS, Spring, ASP.NET, FastAPI, or another profile.
- A pack needs runtime route/middleware discovery or CommonJS/ESM handling.

## Framework-specific risks and invariants

- Route and middleware order is behavior; dynamic registration changes matching and error handling.
- Request/response mutation and shared state can live in locals, closures, globals, or AsyncLocalStorage.
- Async, callback, stream, and process-level errors vary by Node/framework version.
- CommonJS/ESM, dynamic imports, monkey patches, sessions, templates, and middleware hide behavior.

## Workflow

1. Lock Node, package manager/lock file, Express, module mode, middleware, session, template, persistence, auth, and test versions.
2. Fingerprint runtime route stack/order, middleware/error middleware, body parsers, request/response mutations, sessions/cookies, static/templates, locals/context, module loading, process signals, and providers.
3. Extract FCM plus ordered pipeline and Node lifecycle/dynamic-module facts.
4. Select a target profile and map route order, middleware stages, errors, context, streams, sessions, and shutdown explicitly.
5. Implement one complete route or background workload with target code, tests, source maps, and operational hooks.
6. Run source/target startup plus route-order, short-circuit, async/callback/stream error, session, security, provider, and shutdown tests.
7. Run holdout cases for dynamic registration, nested routers, middleware mutation, CommonJS/ESM, streams, and process handlers.
8. Publish dynamic limitations and strangler options for unsafe static migration.

## Required repository outputs

- `framework-packs/express-node-to-<target>/`
- Runtime route/middleware/module fingerprint
- Ordered pipeline and lifecycle contracts
- Target mappings/adapters/source maps
- Dynamic obligations
- Holdout/certification artifacts

## Verification

- Run the real Node source and capture route/middleware order.
- Run target build/startup and compare HTTP/error/session/stream/lifecycle/provider contracts.
- Test graceful shutdown and in-flight requests.
- Run holdout and the gate.

## Stop and escalate when

- Dynamic route or middleware registration is active but unobserved.
- Middleware order is treated as irrelevant.
- Async or stream errors are swallowed.
- Shared/global context would leak across requests.

## Definition of done

The Express/Node pack discovers real runtime ordering and dynamic behavior, migrates a representative workload, passes pipeline/error/session/stream/lifecycle and holdout tests, and blocks unsafe dynamic cases.
