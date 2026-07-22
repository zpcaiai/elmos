---
name: source-target-provenance-map
description: Maintain source PSP to UIR transformation mappings and reserve target trace links. Use for audit, split/merge/desugar, agent/manual edits, or migration evidence queries.
---
# Source Target Provenance Map
Read `../references/uir-v1.md`. Record direct/normalized/desugared/merged/split/synthesized/wrapper/agent/manual/opaque/deleted-with-proof relations, confidence, transformations and notes. Preserve every member of one-to-many and many-to-one mappings and forward target-location placeholders to Batch 4. Every UIR node must trace to PSP or a synthesized reason; canonicalization must never break the chain.
