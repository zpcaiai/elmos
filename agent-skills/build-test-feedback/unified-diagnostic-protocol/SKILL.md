---
name: unified-diagnostic-protocol
description: "Normalize compiler, package, analyzer, test, runtime, database, and sandbox failures into the Batch 8 Diagnostic protocol. Use when ingesting heterogeneous tool output."
---
# Unified Diagnostic Protocol
Read `../references/batch-8-repair-loop.md` and validate records against `contracts/repair-loop-schema/unified-diagnostic.schema.json`.

Preserve native code, redacted original message, phase, module, location, related declaration/test and raw evidence reference. Remove volatile paths, timestamps, run IDs and line numbers only from the fingerprint. Keep assertion, environment and code failures distinct.

Do not duplicate one failure because a tool emitted it in multiple formats. Do not invent a location or overwrite native semantics with the unified category.
