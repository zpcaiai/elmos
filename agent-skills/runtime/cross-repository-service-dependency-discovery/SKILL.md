---
name: cross-repository-service-dependency-discovery
description: Discover evidence-bound service, message, data, file, model, batch, and external dependencies across repositories. Use when constructing or refreshing a Batch 13 system dependency graph.
---

# Cross-Repository Service Dependency Discovery

## Evidence order

Prefer declared contracts, direct static references, build/deployment configuration, gateway or mesh configuration, runtime traces, broker metadata, database audit, log correlation, and customer declarations. Name similarity alone is never a formal edge.

## Workflow

1. Enumerate connected and external repositories, deployables, jobs, endpoints, topics, queues, schemas, stores, files, models, auth systems, and scheduled triggers.
2. Create typed, directional, environment-specific edges with first/last observation time, count, confidence, validity, and raw evidence references.
3. Detect strongly connected components, self-loops, shared database writers, hidden batch access, and external or unknown consumers.
4. Keep `ACTIVE`, `DORMANT`, `HISTORICAL`, `SUSPECTED`, `STALE`, and `UNVERIFIED` distinct.
5. Block ordering or deletion on unresolved hard dependencies, unknown consumers, incomplete coverage, or unsupported cross-environment inference.

## Outputs

Emit a deterministic edge catalog, SCC list, shared-data coupling report, unknown-consumer list, confidence rationale, and discovery blockers. Every edge must lead back to original evidence.
