---
name: database-target-profile-and-migration-strategy-planner
description: Compare database and data-platform targets and construct a governed migration DAG from transaction semantics, SQL and procedure compatibility, CDC, rollback, availability, residency, cost, and team constraints. Use for in-place upgrade, same-engine or heterogeneous replatform, decomposition, analytics offload, lakehouse, and archive decisions.
---

# Database Target Planning

## Generate candidates

- Generate multiple target candidates; never preselect PostgreSQL, a cloud database, Iceberg, Delta, or a BI vendor.
- Keep in-place upgrade, same-engine replatform, managed same-engine, heterogeneous replatform, database decomposition, read-scale offload, analytics offload, lakehouse modernization, and archive-only strategies distinct.
- Source concrete versions and managed-service capabilities from a versioned compatibility registry.

## Compare feasibility

- Score transaction semantics, procedures, SQL, extensions, HA/DR, latency, throughput, volume, growth, region, license, skills, managed-service limits, CDC, rollback, BI, analytics, and operational readiness.
- Keep the OLTP target and analytical target separate.
- Include stored-routine conversion, application changes, data movement, dual run, validation, cutover, and decommission costs.
- Classify each candidate FEASIBLE, FEASIBLE_WITH_ADAPTER, FEASIBLE_WITH_REDESIGN, PILOT_REQUIRED, BLOCKED, or UNKNOWN.

## Build the DAG

- Order discovery, workload capture, feasibility, schema, procedure, query, provisioning, bulk load, CDC, dual run, reconciliation, read cutover, write cutover, stability, and decommission.
- Include approvals for lossy conversion, replication changes, target provisioning, and writer cutover.
- Block the plan when no candidate satisfies authoritative transaction, data residency, recovery, or compatibility constraints.
