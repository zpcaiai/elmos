# Batch 15 verification: Database and Data Platform Modernization Engine

Verified on macOS on 2026-07-21. This report separates repository implementation from customer database, data movement, CDC, lakehouse, BI, governance, and production-cutover evidence.

## Repository-complete scope

- The independent Java 21 database-data worker implements the shared engine API, tenant-scoped idempotency, six separate fail-closed Runner profiles, and three independent OLTP, analytical, and BI semantic tracks.
- The deterministic core covers target candidate selection, the ordered migration lifecycle, canonical parser/AST/IR obligations, data cutover aggregation, and all 24 required incident decisions.
- The Java control plane exposes only data-domain capabilities and cutover evidence evaluation. It cannot connect to customer databases, launch vendor CLIs, change logging, start CDC, write production data, switch writers, approve metrics, or decommission sources.
- V15 creates 85 tenant-scoped projections with forced RLS, extends and reuses V13 CDC authorities, and adds append-only result and evidence histories.
- Five Draft 2020-12 JSON Schemas, five fixtures, OpenAPI 3.1, a Runner policy/manifest, D001–D014 Skills, and ADR-0037 are present.

## Local verification

| Gate | Result |
|---|---|
| Database Data Engine | 40 tests passed: 24 required incidents plus loss-preserving Canonical Schema/SQL/Procedure IR, CDC Provider port, unified Evidence/Risk/Check/Cost mapping, Runner permissions, three-track planning, lifecycle, cutover aggregation, tenant idempotency, fail-closed execution, five Schema fixtures, OpenAPI/policy, and controller checks. |
| Java/Maven reactor | Full clean verify produced 69 Surefire reports containing 318 tests, 0 failures, 0 errors, and 1 Docker-dependent skip. |
| PostgreSQL 17 | V1–V15 executed in order against a fresh direct instance: 753 public tables, 752 tenant-isolation policies, 753 organization_id columns, and 66 append-only triggers. |
| Batch 15 persistence | All 87 named objects exist: 85 new V15 tables plus the two reused V13 cdc_streams/cdc_offsets authorities. Two non-owner tenant sessions each saw exactly their own estate row, and an update to data_quality_results was rejected by the append-only trigger. |
| Skills | D001–D014 passed quick_validate.py; generated agents/openai.yaml metadata and all JSON assets parsed without TODO/TBD/placeholder markers. Inventory is now 35 Build and 132 Runtime Skills. |
| Contracts | Five Draft 2020-12 Schemas, five fixtures, the 24-scenario manifest, Runner policy/manifest, and OpenAPI 3.1 contract parsed; executable fixture checks passed. |
| HTTP worker | The packaged Java 21 worker started on an isolated local port; capabilities returned all three tracks and six NOT_CONFIGURED Runners. Scan returned terminal FAILED, DATABASE_RUNNER_REQUIRED, empty evidence, executed=false, and customerCodeExecuted=false. |
| Compose | docker compose config accepted the database-data worker service and its isolated port. |
| Frontend Client regression | TypeScript strict build and all 34 Node tests passed. |
| .NET regression | 12 tests passed. |
| Python regression | 31 tests passed; Ruff and strict mypy passed across 19 source files. |
| Web console | TypeScript and Next.js 16.2.10 production build passed; / and /_not-found were statically generated. |

The sole Maven skip is the Testcontainers Flyway test because no Docker API was available. It is not counted as success; the direct PostgreSQL execution supplied current V1–V15 SQL, RLS, tenant-isolation, object-reuse, and append-only evidence instead. The temporary database was stopped and moved to macOS Trash for recoverable cleanup.

## Fail-closed external gates

The following remain NOT_BUILT, UNAPPROVED, NOT_CONFIGURED, NOT_RUN, or BLOCKED until authorized evidence exists:

1. Build, license, scan, attest, and approve Oracle, SQL Server, MySQL, PostgreSQL, Data Platform, and BI Validation Runner images/hosts and native toolchains.
2. Lease real customer read-only discovery credentials and capture complete estate, workload windows, writers, consumers, routines, jobs, cross-database dependencies, classification, ownership, capacity, and growth.
3. Select concrete target products/versions from a customer-approved compatibility registry and provision isolated source/target environments.
4. Execute real schema, SQL, procedure, trigger, job, application-query, pipeline, lakehouse, report, and semantic-layer conversion.
5. Run consistent full load and CDC from the same SCN/LSN/GTID/checkpoint; prove offset restart, DDL handling, large transactions, conflicts, lag, and reverse-path behavior.
6. Run representative result, transaction, concurrency, performance, full critical-data reconciliation, business invariants, BI metric, row-security, refresh, lineage, masking, residency, retention, and deletion validation.
7. Obtain named read/write cutover approvals; observe every source writer, hold stability, exercise rollback including target-only data, make the source read only, archive, and decommission.

No static policy result, unit test, fixture, generated candidate, local PostgreSQL migration, or HTTP capability response proves a customer migration, near-zero downtime, data equivalence, BI equivalence, production rollback, or decommission.
