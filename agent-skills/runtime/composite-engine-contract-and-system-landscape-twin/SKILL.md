---
name: composite-engine-contract-and-system-landscape-twin
description: Build an immutable, versioned cross-language System Landscape Twin above the Java, .NET, and Python engines. Use for Batch 13 discovery, topology baselining, system inventory, or composite readiness decisions.
---

# Composite Engine Contract and System Landscape Twin

## Boundary

Act as a system-level orchestrator, never a fourth source transformation engine. Do not edit source, bypass language engines, accept business risk, switch production writes, delete legacy data, or decommission assets.

## Workflow

1. Bind every node and edge to one organization, environment, observation time, source snapshot, and evidence reference.
2. Merge repositories, artifacts, deployables, APIs, messages, databases, files, batch jobs, models, UIs, and external systems without collapsing their native identities.
3. Version the twin immutably. Preserve prior versions and deterministic IDs.
4. Record repository, deployable, runtime, contract, trace, message, database, and external-system coverage separately.
5. Mark suspected, stale, unknown, and incomplete relationships explicitly. Never convert missing evidence into an empty dependency set.
6. Return `LANDSCAPE_INCOMPLETE` when coverage or evidence is incomplete.

## Outputs

Emit `system-landscape.json`, `system-nodes.json`, `system-edges.json`, `coverage.json`, `unknowns.json`, and an evidence index. A `complete` claim requires full declared coverage and no unresolved unknowns.
