---
name: framework-test-and-fixture-migrator
description: "Migrate framework integration tests, test containers, dependency overrides, clients, security principals, clocks, brokers, caches, databases, and lifecycle fixtures. Use when building Batch 7 verification suites."
---
# Framework Test and Fixture Migrator
Read `../references/afsm-v1.md`. Preserve source-test mappings and migrate route, binding, validation, security, errors, DI scopes, transactions, queries, messaging, cache, scheduler, startup/shutdown, health and OpenAPI coverage.

Keep framework integration tests as integration tests; isolate database/cache/config and restore overrides. Never use permanent security bypasses or fake passing assertions. Mark incomplete tests skipped, pending or explicitly failing with a reason.

