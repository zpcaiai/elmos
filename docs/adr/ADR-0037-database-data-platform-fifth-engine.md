# ADR-0037: Database and data-platform modernization as a fifth execution engine

## Status

Accepted for Batch 15 on 2026-07-21.

## Context

Schema generation does not prove a production database migration. Transaction behavior, procedure language, query results, performance, initial-load/CDC frontiers, data quality, BI metrics, security, lineage, writer ownership, rollback, and decommission span application and data-platform boundaries. OLTP, analytical storage, and BI semantics also have different authorities and acceptance criteria.

## Decision

Add an independently deployable Java 21 ELMOS_DATABASE_DATA worker. Reuse the existing engine API, Tenant, Workflow, Runner, Risk, Approval, Evidence, Portfolio, Delivery, Audit, Billing, and Composite authorities.

Keep three distinct tracks: OLTP_DATABASE, ANALYTICS_PLATFORM, and BI_SEMANTIC. Join them only in a system cutover decision. Parse vendor schema, SQL, and procedures into separate canonical semantic models; preserve vendor extensions and block unresolved semantics.

Declare Oracle, SQL Server, MySQL, PostgreSQL, Data Platform, and BI Validation Runner profiles. Discovery is read only. Vendor CLIs, customer connections, target provisioning, bulk load, CDC, DDL, DML, log changes, writer cutover, and decommission run only in capability-matched external Runners with short-lived job credentials and named approval.

Use Near-zero Downtime terminology. Require a consistent initial-load and CDC frontier, recoverable offsets, DDL control, reconciliation, workload performance, data quality, BI security, governance, complete writer inventory, and a validated rollback path before write cutover.

## Consequences

- The control plane evaluates evidence and authority but never connects to a customer database.
- In-place, same-engine, heterogeneous, decomposition, analytics offload, lakehouse, and semantic targets remain comparable candidates rather than product defaults.
- V15 creates 85 tenant-scoped data projections and reuses the V13 CDC stream and offset authorities.
- D001–D014 define reusable operating contracts; 24 executable incident scenarios are the repository acceptance minimum.
- No unit test, schema fixture, plan, or synthetic policy result proves that customer data moved, CDC caught up, BI metrics matched, or a production cutover can roll back.

## External gates

Customer topology and credentials, licensed vendor clients, approved Runner images, source logs, target platforms, CDC providers, representative workloads, privacy-safe data, BI tenant APIs, lineage/catalog providers, business owners, production approvals, stability telemetry, rollback drills, and decommission evidence remain NOT_CONFIGURED or NOT_RUN until supplied and independently verified.
