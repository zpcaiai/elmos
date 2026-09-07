---
name: data-serialization-boundary-mapper
description: Map cross-runtime data contracts and serialization semantics, including evolution and compatibility. Use for wrappers, sidecars, remote services, and retained runtimes.
---
# Data Serialization Boundary Mapper
Read `../references/dependency-migration-v1.md`. Define schema IDs/versions, field identity, null/missing/default distinctions, numbers/decimal precision, timestamps/time zones, enums, maps/order, bytes/encoding, polymorphism, references/cycles, exceptions, limits and unknown-field behavior. Generate schemas and conversion plans plus forward/backward compatibility tests. Never infer wire compatibility from similar classes, use unsafe native serialization, lose precision silently, accept unbounded payloads, or evolve contracts without compatibility policy.
