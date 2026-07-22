---
name: database-data-platform-elmos-unified-evidence-integration
description: Map database, CDC, quality, lakehouse, pipeline, BI, lineage, governance, cutover, and decommission evidence into ELMOS risk, portfolio, checks, audit, cost, delivery, and offline evidence packs. Use when integrating database-data results with application PRs and system-level migration governance.
---

# Unified Database and Data Evidence

## Reuse authorities

- Reuse Organization, System Landscape, Portfolio, Plan, Step, Risk, Approval, Evidence, Delivery Snapshot, Audit, Billing, and Customer Success authorities.
- Add a DATABASE_DATA_PLATFORM scope and a versioned ELMOS_DATABASE_DATA evidence extension; do not create parallel tenant, workflow, approval, or billing stores.
- Link database assets and writer cutovers to affected application, client, pipeline, and BI changes.

## Map evidence and risk

- Map estate, workload, canonical IR, schema, SQL, procedure, load, CDC, reconciliation, performance, quality, lakehouse, data product, semantic model, BI, lineage, governance, cutover, and decommission artifacts.
- Map type loss, procedure redesign, CDC lag, query regression, BI metric difference, masking loss, unknown writer, and missing reverse replication to explicit ELMOS risks.
- Build a composite change set covering target schema, procedures, application SQL, CDC, pipelines, BI, access, cutover, and decommission.

## Enforce gates

- Require schema compatibility, procedure behavior, reconciliation, query performance, CDC readiness, data quality, BI metrics, governance, cutover, and decommission checks.
- Make system and data gates stronger than DDL generation success.
- Meter discovery, object/procedure conversion, query validation, load volume, CDC hours, quality runs, compute, BI artifacts, lineage events, and cutover operations.
- Audit credential leases, lossy mappings, trigger removal, CDC startup, metric and access changes, writer switch, source read-only, deletion, and decommission.
- Package immutable, content-addressed, offline-verifiable evidence; preserve NOT_RUN for absent external execution.
