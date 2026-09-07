---
name: standard-library-mapping-engine
description: Map used APIs to target SDK, BCL, or standard-library facilities with explicit semantic adaptations. Use before adding third-party target packages.
---
# Standard Library Mapping Engine
Read `../references/dependency-migration-v1.md`. Prefer target standard facilities only when the target runtime version and platform support every required API and behavior. Produce API-by-API mappings, conversions, imports, error/lifecycle adaptations, gaps and tests. Treat dates/time zones, path normalization, regex dialects, randomness, encodings, decimal precision, collection ordering, I/O and concurrency as semantic risk areas. Do not equate familiar names or convenience with fidelity; unsupported operations fall through to another strategy.
