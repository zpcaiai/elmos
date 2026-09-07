---
name: test-discovery-layering-and-selection-engine
description: "Discover, index, layer, and select Batch 8 parser, unit, module, contract, integration, startup, cross-runtime, and full-regression tests. Use before executing migrated tests."
---
# Test Discovery Layering and Selection Engine
Read `../references/batch-8-repair-loop.md`. Record stable test ID, layer, module, declarations, tags, duration, resources and source test. Select direct, same-type, module, dependent, contract/integration and full tests in order with reasons.

Treat discovery failure or unexpected zero tests as blocking. Validate filter syntax. Do not let high-risk patches stop at unit tests or incremental selections replace the final full regression.
