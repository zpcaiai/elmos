---
name: method-body-lowering-orchestrator
description: Orchestrate faithful-first UIR method-body generation into a Batch 4 target skeleton. Use whenever lowering callables, scheduling recursive groups, generating implementation patches, or coordinating Batch 5.
---
# Method Body Lowering Orchestrator
Read `../references/lowering-v1.md` completely before planning a run.

Verify the Batch 4 module gate and all UIR/skeleton/profile identities. Order pure/value/domain/application/infrastructure/entry callables by the call graph; treat SCCs as recursive units. Create one immutable plan per callable, select deterministic rules, emit and validate Faithful code, optionally run Level 1/2 idioms, validate again, atomically patch the mapped declaration, and update provenance.

Isolate failures per callable. Cache only by UIR hash, rule versions, target profile and generator version. Never run idiomatization before Faithful validation or create a duplicate method when its Target Declaration ID is missing. Send unresolved work to a bounded agent/manual queue and emit the full run, coverage and module-gate reports.
