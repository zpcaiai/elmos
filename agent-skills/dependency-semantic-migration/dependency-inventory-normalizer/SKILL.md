---
name: dependency-inventory-normalizer
description: Normalize Maven, NuGet, Python, npm, and other dependency declarations into stable Batch 6 coordinates with scope, provenance, and resolution state. Use at Batch 6 intake.
---
# Dependency Inventory Normalizer
Read `../references/dependency-migration-v1.md`. Merge Build Model declarations, lock evidence, plugins, tools, runtimes, optional/peer/dev/test scopes, private sources, and vendored/native artifacts without collapsing their meanings. Emit deterministic dependency IDs, declared and resolved versions, project ownership, direct/transitive state, source and unresolved issues. Keep build-time, test-time, runtime, optional, peer, native, and service dependencies distinct. Never invent an ecosystem, version, scope, source, or resolution state; malformed and unresolved records block D-A rather than disappearing.
