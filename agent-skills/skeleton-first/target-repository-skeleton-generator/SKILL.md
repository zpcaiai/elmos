---
name: target-repository-skeleton-generator
description: Create the idempotent target repository layout, modules, build entry, migration metadata, and protected generated/manual regions. Use for Batch 4 repository emission.
---
# Target Repository Skeleton Generator
Read `../references/skeleton-v1.md`. Create language-appropriate src/tests/config/resources/migration/docs/build structure plus README, ignore/editor/encoding/license/TODO/generated declarations and generation manifest. Bind every file to generation/source/uir/profile IDs. Never copy secrets, unknown binaries or vendor trees, overwrite human files, or mix generated/manual ownership; reruns are idempotent and conflicts become patches/reports.
