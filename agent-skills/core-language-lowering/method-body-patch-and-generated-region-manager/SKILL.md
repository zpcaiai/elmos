---
name: method-body-patch-and-generated-region-manager
description: Atomically patch verified callable bodies into Batch 4 generated regions while protecting manual code and stable target IDs. Use for generation, regeneration, merge, conflict, or rollback.
---
# Method Body Patch and Generated Region Manager
Read `../references/lowering-v1.md`. Default to one reversible patch per callable. Locate by parsed symbol and Target Declaration ID, verify base hash, and replace only a placeholder or unchanged generated region. Use three-way merge for modified generated content; reject manual/missing/conflicting targets.

Never identify solely by line numbers, partially apply a failed patch, overwrite manual regions or omit helper provenance. Record before/after hashes, UIR operations, rules and obligations. Repeated identical generation must be a no-op, and each patch must roll back independently.
