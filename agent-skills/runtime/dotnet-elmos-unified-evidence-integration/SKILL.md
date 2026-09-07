---
name: dotnet-elmos-unified-evidence-integration
description: Map .NET-specific inventories, findings, plans, transformations, validation, cost, risk, audit, SCM and delivery into existing ELMOS tenant-scoped objects.
---

# .NET and ELMOS Unified Evidence Integration

Use the existing organization, repository, snapshot, workflow, approval, Runner lease, audit, usage/billing, risk, SCM, evidence-pack, rollback, portfolio and delivery objects. Do not create a second control plane.

## Mapping

Map .NET jobs to shared engine jobs and leases; technology/portability issues to shared findings/risks; .NET migration steps to the shared plan/DAG/executor model; Roslyn/project/ASP.NET/WCF/EF artifacts to versioned .NET evidence extensions; model/tool usage to the existing usage ledger; and final checks/PR/evidence pack/rollback/acceptance to existing delivery governance.

Every extension must include organization, immutable snapshot/commit, engine and version, schema version, artifact type, content hash, status, provider/method/version and source evidence. Keep engine internals in the extension payload rather than adding Roslyn types to Java domain code.

For mixed Java/.NET portfolios, require the same organization and portfolio, then combine API dependencies, waves, risks and acceptance gates. Do not merge job histories or evidence identities across engines.

## Promotion rule

Only shared workflow and independent validation policy may promote. `NOT_RUN`, `BLOCKED`, `INCONCLUSIVE`, missing signatures, stale HEAD, expired leases, cross-tenant references, unapproved spend, or missing rollback evidence prevents delivery.

## Required output

Produce valid .NET evidence extensions, shared object references, risk/cost/audit links, portfolio wave mapping, SCM checks, evidence-pack manifest and rollback/acceptance status without duplicating authorization, billing or delivery state.
