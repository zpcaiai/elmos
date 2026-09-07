---
name: composite-elmos-evidence-and-portfolio-integration
description: Map Batch 13 system artifacts into shared ELMOS evidence, tenant, audit, portfolio, billing, SCM, and delivery contracts. Use when aggregating composite results without duplicating the platform.
---

# Composite ELMOS Evidence and Portfolio Integration

## Rules

Reuse the existing tenant, identity, authorization, workflow, Runner, model gateway, usage, audit, SCM, delivery, retention, and evidence-pack systems. Do not create a second control platform or overwrite language-engine facts.

## Workflow

1. Bind every artifact to organization, landscape version, source snapshots, engine versions, schema version, status, content hash, time, and evidence references.
2. Preserve evidence layers: language engine, repository, contract, data, runtime, business journey, and `COMPOSITE_SYSTEM`.
3. Use deterministic canonicalization and content hashes. Append new evidence rather than mutating observations or decisions.
4. Aggregate Java, .NET, and Python repository plans into portfolio waves while keeping their native evidence reachable.
5. Place the system gate above repository gates; green language engines do not imply system success.
6. Emit external capability status as `NOT_CONFIGURED`, `NOT_RUN`, `BLOCKED`, or `INCONCLUSIVE` rather than fabricated completion.

## Outputs

Emit composite evidence extensions, portfolio status, blockers, usage attribution, audit links, delivery references, and an evidence index suitable for Batch 8 packaging and Batch 9–10 governance.
