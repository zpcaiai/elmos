---
name: api-adaptation-planner
description: Design target-facing adapters for signatures, types, errors, async, callbacks, configuration, serialization, and resources. Use when a selected candidate needs adaptation.
---
# API Adaptation Planner
Read `../references/dependency-migration-v1.md`. Define source facade, target calls, type/null/error/async/lifecycle transformations, API mapping table, placement, generated ownership, observability and validation obligations. Keep adapters narrow and tied to actually used APIs. Prefer explicit conversion over hidden behavior. Never place framework policy in a library adapter, swallow exceptions, change cancellation or retry behavior silently, expose secrets, or call an adapter complete while required APIs remain unmapped.
