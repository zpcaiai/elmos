---
name: deterministic-skeleton-formatter-and-patch-manager
description: Format, sort, hash, regenerate, and patch skeleton files while protecting manual work. Use after emission or on incremental regeneration.
---
# Deterministic Skeleton Formatter and Patch Manager
Read `../references/skeleton-v1.md`. Pin formatter/convention versions, stable ordering, line endings, headers and generated/manual region IDs. Support create/update-generated/rename/move/delete-generated/preserve-manual/conflict with hashes, source-map updates and rollback. Never overwrite unknown manual code, delete modified generated files, or reorder imports if binding could change. Same input must yield empty diff.
