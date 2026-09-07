---
name: dependency-injection-and-lifetime-migrator
description: "Migrate framework providers, qualifiers, factories, scopes, optional/lazy bindings, cycles, and cleanup. Use when translating DI containers or explicit dependency factories."
---
# Dependency Injection and Lifetime Migrator
Read `../references/afsm-v1.md`. Preserve provider contract/implementation, qualifier, selection, scope, request cache, factory call count, lazy/eager and cleanup semantics.

Build and validate the target dependency graph. Block longer-lived providers that capture shorter-lived resources. Resolve cycles explicitly with responsibility changes, factories, interfaces or controlled lazy references; do not introduce an unbounded service locator.

