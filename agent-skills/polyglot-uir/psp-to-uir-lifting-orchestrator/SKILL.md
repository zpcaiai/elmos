---
name: psp-to-uir-lifting-orchestrator
description: Orchestrate deterministic PSP-to-UIR lifting and incremental passes. Use for any eligible Batch 2 module entering Batch 3.
---
# PSP to UIR Lifting Orchestrator
Read `../references/uir-v1.md`. Verify PSP conformance per module, then lift declarations, types, bodies, structured flow, CFG/SSA, effects, exceptions, async, aliases, canonicalization, obligations, mappings, and conformance in dependency order. Record every pass/version/input/output. Never overwrite a prior valid UIR on pass failure or drop PSP/language extensions silently. Emit the run manifest and partial module diagnostics.
