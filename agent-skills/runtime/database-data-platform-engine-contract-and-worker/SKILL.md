---
name: database-data-platform-engine-contract-and-worker
description: Implement or review the isolated ELMOS database and data-platform worker, vendor Runner routing, capability contract, short-lived credentials, approvals, and fail-closed execution. Use for database-engine APIs, worker boundaries, Oracle, SQL Server, MySQL, PostgreSQL, CDC, lakehouse, BI, and data-platform execution jobs.
---

# Database and Data Platform Engine

## Preserve the boundary

- Keep Tenant, Workflow, Risk, Approval, Evidence, Delivery, Audit, and Billing authoritative in the ELMOS control plane.
- Deploy ELMOS_DATABASE_DATA independently and expose GET capabilities, POST scan, plan, execute-step, validate, GET job, and POST cancel operations under /engine/v1.
- Route Oracle, SQL Server, MySQL, PostgreSQL, and data-platform work to separate capability-matched Runners.
- Keep OLTP, analytics, and BI semantic work as separate tracks even when a composite gate joins their evidence.

## Enforce execution safety

- Give discovery jobs only metadata, catalog, plan, and performance-view read capabilities.
- Require named approval before DDL, DML, replication administration, logging changes, CDC startup, or authoritative-writer cutover.
- Lease credentials per job, exclude them from prompts, reports, and ordinary logs, and revoke them after the job.
- Never execute customer code or vendor CLIs in the control-plane process.
- Return failed or blocked with empty evidence when a required Runner, target, permission, provider, or independent validator is absent.

## Produce governed results

- Bind every result to organization, immutable input snapshot, engine version, policy version, job, and content hash.
- Emit vendor-neutral evidence references and retain provider-specific details only in a versioned extension.
- Use Near-zero Downtime wording; do not claim zero downtime without log capture, frontier consistency, recoverable offsets, writer control, reconciliation, and rollback evidence.
- Clean temporary environments without deleting immutable evidence.

## Reject

- Reject cross-tenant access, changed-input idempotency reuse, long-lived credentials, unapproved production writes, dual uncontrolled writers, fabricated success, and evidence without provenance.
