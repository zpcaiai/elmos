# AFSM v1 framework migration protocol

## Contents

1. Inputs and evidence boundary
2. Entity and recipe contracts
3. Concern-specific invariants
4. Workflow and artifacts
5. Gates and completion claims

## 1. Inputs and evidence boundary

Require all of the following before generation:

- a frozen source snapshot and UIR run;
- Batch 4 target profile, module map and skeleton;
- Batch 5 generated-core status and open obligations;
- Batch 6 D-D admission for each module entering Batch 7;
- code-plus-configuration framework evidence with exact versions;
- an approved recipe catalog and target dependency policy;
- native target emitter and isolated startup/discovery authority.

Treat `NOT_RUN`, `INCONCLUSIVE`, missing authority and missing provenance as blocking. Never infer framework behavior from a single dependency, annotation or decorator. Never execute a customer application merely to fill a static-model gap; request an approved isolated runtime analysis instead.

Supported initial families are Spring Boot MVC/WebFlux, FastAPI, ASP.NET Core Controllers/Minimal APIs, NestJS Express/Fastify and Express. Distinguish each programming and runtime mode.

## 2. Entity and recipe contracts

Use AFSM entity envelopes from `contracts/framework-schema/afsm-entity.schema.json`. Every entity must include:

- AFSM version 1.0, stable ID and supported kind;
- source framework/version and selected target framework;
- target module;
- explicit semantic attributes and related entity IDs;
- UIR source-map IDs;
- extractor/rule/version/confidence/timestamp/evidence provenance;
- obligation IDs for every unresolved or conditional behavior.

Entity kinds cover application/module/component/provider/lifecycle scope; HTTP pipeline components/endpoints/binding/response/errors; validation/security; ORM/repository/query/unit-of-work/transactions; configuration; messaging; cache; scheduling/background work; and startup/shutdown/health.

Use recipes from `contracts/framework-schema/framework-recipe.schema.json`. Select only production, tested, idempotent recipes whose source/target framework and version ranges match. Reject equal-specificity/equal-priority conflicts. Reject required dependencies absent from the target approval set. Preserve the selected recipe ID/version, alternatives, transformations, dependencies, tests, provenance and obligations.

Delegate code creation to native AST/CST/LST backends. Require the backend to return parsed, registered, deterministic, non-placeholder emissions with target semantic claims, source maps and artifact references. Do not use large text templates as a production backend.

## 3. Concern-specific invariants

### HTTP, routes and binding

- Reconstruct actual middleware/filter/interceptor/guard order from registration, explicit order, defaults and conditions.
- Preserve short-circuit, async and error paths. Authentication must precede authorization.
- Compare route path, method, host/header/query/media constraints, precedence, status and API version.
- Preserve missing/null/empty/default/multi-value distinctions, content negotiation, unknown-field policy, Decimal/time/enum/polymorphism serialization and streaming.
- Block duplicate target routes or protected endpoints without both authentication and authorization entities.

### DI and lifecycle

- Preserve scope, request caching, factory call count, lazy/optional/qualified bindings, conditional registration and cleanup.
- Block a longer-lived provider that captures a shorter-lived provider.
- Resolve cycles explicitly; do not introduce an unbounded service locator.
- Keep request cleanup separate from application shutdown.

### Validation and errors

- Model binding coercion separately from validation and domain invariants.
- Preserve nested/cross-field/groups/custom/async validation and error status/code/path/localization/collection behavior.
- Do not echo sensitive rejected values.
- Preserve exception handler specificity, cause, async rejection and partial-response risk. Do not expose stack traces by default.

### Persistence and transactions

- Preserve schema/table/column/key/generation/nullability/precision/scale/relation/cascade/orphan/loading/tracking/concurrency/tenant metadata.
- Preserve query filter/join/order/null order/projection/pagination/locking/timeout/tracking/streaming and parameter binding.
- Block unbounded client-side evaluation, unstable pagination, raw-SQL concatenation and silent N+1/loading changes.
- Preserve transaction boundary, propagation, isolation, read-only, timeout, rollback, proxy/self-invocation behavior and async context.
- Never reduce `requires-new` to `required`; address multi-resource atomicity with explicit outbox/saga/manual strategy.

### Authentication and authorization

- Preserve credential source, token verification, issuer/audience/algorithm/clock skew, cookie/session/CSRF properties, challenge and forbid behavior.
- Never copy passwords, signing keys, client secrets or MFA material; emit secret references only.
- Normalize authorization to an AND/OR/NOT role/claim/permission/owner/tenant/time/custom tree before lowering.
- Preserve default deny/allow, route plus method security, role/authority distinctions, resource-loading order and 401/403 behavior.
- Require human review evidence for Agent-generated security code.

### Configuration

- Preserve key hierarchy, source, precedence, profile/environment, required/default/type validation, reload and test override.
- Make environment-key mapping reversible across dots, colons, underscores, case and nesting.
- Store only secret references. Required missing configuration must fail startup.

### Messaging, cache and scheduling

- Preserve broker/destination/schema/key/header/group/concurrency/ack/delivery/order/retry/DLQ/idempotency/transaction/outbox/rebalance/shutdown behavior.
- Do not claim absolute exactly-once; state broker, producer, consumer and transaction guarantees separately.
- Preserve cache backend/key/tenant namespace/TTL/sliding/null/serialization/stampede/invalidation/fail-open and transaction order. Block missing tenant key isolation.
- Classify request-local tasks, in-process schedules, durable jobs, workers and external schedules separately.
- Convert cron dialect, timezone, DST, fixed-rate/fixed-delay, misfire, concurrency, leases and shutdown. Never downgrade a durable job to an in-memory timer.

### Startup, health and shutdown

- Preserve configuration/dependency/startup/warmup/ready/running/draining/shutdown/disposed phases and ordering.
- Do not report readiness before required dependencies are ready.
- Separate liveness from transient dependency health; health checks must be non-destructive and non-secret-bearing.
- Require graceful drain and cleanup evidence for HTTP, consumers, schedulers, pools and model/runtime resources.

## 4. Workflow and artifacts

1. Fingerprint family, mode, version and extensions from at least two independent evidence kinds.
2. Lift code, annotations/decorators/attributes/builders and configuration into AFSM using an authoritative adapter.
3. Validate entity IDs, kinds, relationships, source maps and provenance.
4. Select deterministic production recipes and create blocking obligations for unsupported or conditional semantics.
5. Delegate patches to the native target framework backend; preserve source maps and target semantic claims.
6. Compare source AFSM attributes with target claims. Accept a difference only with explicit verified-equivalence evidence; otherwise keep it blocking.
7. Generate or migrate framework tests, fixtures, route/OpenAPI comparisons and concern-specific differential tests.
8. Start only in an isolated environment with production access denied, fake/test resources, scheduler execution disabled and consumer execution disabled during discovery.
9. Record static model, bootstrap, container resolution, discovery, smoke and shutdown separately.
10. Write the manifest, compressed AFSM stream, plans, emissions, diffs, obligations and conformance report outside the target repository.

Use `modules/framework-migration` as the orchestration contract. The core does not install dependencies, mutate lockfiles, run production resources or substitute test doubles for live acceptance evidence.

## 5. Gates and completion claims

- F-A: complete AFSM lift and source maps; endpoint/provider/config/security recipe coverage.
- F-B: safe application bootstrap, DI/container resolution, route discovery, OpenAPI generation and no route/scope/order conflict.
- F-C: endpoint contract, validation, transaction, authentication and authorization strategy thresholds with no open blocking obligation.
- F-D: stricter provider/transaction/messaging/cache/scheduler and trace thresholds, smoke/shutdown evidence and reviewed high-risk Agent output.

Evaluate every target module separately. Repository averages never override a critical-module failure. A passed F-D admits the module to the next verification batch only. It does not prove whole-system behavioral equivalence, production safety or deployment readiness.
