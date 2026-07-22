# Batch 7 AFSM framework migration

`modules/framework-migration` implements the deterministic Batch 7 control plane described by ADR-0033. It fingerprints supported framework families from multiple evidence kinds, accepts an authoritative AFSM lift, chooses reviewed recipes, delegates native generation, compares source and target semantic claims, creates obligations and adjudicates F-A through F-D per target module.

## Implemented offline guarantees

- AFSM v1 entity/provenance/source-map validation and dangling-reference checks.
- Production-only, version-aware, idempotent and deterministic recipe selection.
- No unapproved recipe dependency and no ambiguous equal-ranked recipe selection.
- Route-conflict, protected-endpoint, middleware-order, captive-scope and secret-material gates.
- Exact or evidence-proven target semantic claims for REST, binding, DI, validation, ORM, transactions, security, configuration, messaging, cache, scheduling and lifecycle.
- Explicit rejection of durable-job downgrade, missing tenant cache key and unreviewed high-risk Agent output.
- Injected native emitter and isolated startup/discovery/smoke/shutdown evidence; `NOT_RUN` is never rendered as pass.
- Atomic evidence artifacts, Zstandard AFSM stream and symlink-safe output outside the target repository.

## Required live authorities

1. Source adapters for Spring Boot/MVC/WebFlux, FastAPI, ASP.NET Core, NestJS and Express that jointly analyze code, dependency resolution, framework configuration, generated endpoints and runtime defaults.
2. Native target AST/CST/LST backends for the selected target framework and language. Large string templates are not an approved production backend.
3. Reviewed recipe catalogs with version ranges, tests, dependency policy and provenance.
4. Sandboxed framework environments that use test databases, brokers, caches, secrets and external-service fakes; production access, scheduler execution and consumer execution must be denied during discovery.
5. Route/OpenAPI, DI scope, database/transaction, message, cache, scheduler, security and lifecycle differential harnesses.

## Evidence boundary

The unit tests use deterministic injected authorities. They prove orchestration and fail-closed behavior, not that a real Spring, FastAPI, ASP.NET Core, NestJS or Express repository has been migrated, started or behaviorally validated. F-D is admission to further verification, never a production-equivalence statement.
