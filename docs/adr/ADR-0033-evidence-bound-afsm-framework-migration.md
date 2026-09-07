# ADR-0033: Evidence-bound AFSM framework migration

- Status: Accepted
- Date: 2026-07-21

## Context

Framework migration is not annotation renaming. Route precedence, middleware ordering, dependency scope, coercion, error contracts, ORM tracking, transaction propagation, authentication and authorization, configuration precedence, messaging acknowledgement, cache invalidation, scheduler durability and application lifecycle all affect behavior.

Maintaining every source-to-target framework pair would duplicate those concerns and make provenance and validation inconsistent. The repository also already has a deterministic OpenRewrite recipe-governance subsystem; that subsystem governs recipe artifacts and licensing, but it is not a framework semantic model and cannot stand in for Batch 7.

## Decision

Batch 7 uses Application Framework Semantic Model v1 (AFSM) as the shared framework protocol. Spring Boot/MVC/WebFlux, FastAPI, ASP.NET Core Controllers/Minimal APIs, NestJS Express/Fastify and Express adapters lift code-plus-configuration facts into provenance-bearing AFSM entities. Target framework backends lower selected, versioned, production-tested recipes into native AST/CST/LST patches.

`modules/framework-migration` is an offline orchestration and adjudication core. Framework analyzers, native target emitters and isolated startup/discovery runners are injected authorities. Missing or incomplete authorities produce `BLOCKED`/`NOT_RUN`; the core does not generate text templates, start customer applications, install packages or infer runtime success.

Recipe selection is deterministic. Equal-ranked conflicts, non-production or non-idempotent recipes, missing tests/provenance and unapproved dependencies block. Generated entities must retain UIR source maps and explicit target semantic claims. A changed claim requires verified equivalence evidence or a blocking obligation.

The gate is non-compensating. Protected endpoints require both authentication and authorization, authentication precedes authorization, secrets never enter AFSM or generated artifacts, long-lived providers cannot capture shorter-lived providers, durable jobs cannot become in-memory timers, tenant cache keys cannot lose tenant isolation, and high-risk Agent security/transaction patches require human review evidence.

F-A through F-D are evaluated per target module. Safe isolated bootstrap, container resolution, route/OpenAPI discovery, smoke and shutdown evidence is required for F-D. F-D means eligible for the next verification batch; it is not production readiness or whole-system behavioral equivalence.

## Consequences

- Adding another framework requires one source adapter and/or one target backend, not every pairwise converter.
- Runtime defaults become inspectable data rather than hidden assumptions.
- Boundary differences remain explicit obligations and can be closed only by named evidence or audited waiver.
- The current repository proves orchestration, fail-closed gates, artifact safety and deterministic recipes with injected test doubles. Real migrations still require the native framework adapters, emitters and isolated runtime environments named above.
