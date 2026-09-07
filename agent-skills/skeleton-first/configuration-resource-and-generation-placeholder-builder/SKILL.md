---
name: configuration-resource-and-generation-placeholder-builder
description: Plan target configuration, resources, schemas, migrations, codegen, and external assets without executing or leaking them. Use for non-source Batch 4 inventory.
---
# Configuration Resource and Generation Placeholder Builder
Read `../references/skeleton-v1.md`. Map each config/resource to copy/transform-later/reference/exclude/manual with environment schema, secret reference, binding type, defaults/required, migration/codegen manifests, inputs/outputs/license/reproducibility. Never copy secrets/private keys, execute migrations/generators, edit generated output manually, or change production defaults. Unknown binaries require license/manual review.
