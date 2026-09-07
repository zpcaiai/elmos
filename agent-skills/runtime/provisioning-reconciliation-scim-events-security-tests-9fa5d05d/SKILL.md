---
name: provisioning-reconciliation-scim-events-security-tests-9fa5d05d
description: "Implement provisioning reconciliation, entitlement drift detection, optional RFC 9967 SCIM events, protocol conformance tests, security attack tests, recovery tests, and mandatory release evidence."
---

# Objective

Prove that federation, provisioning, hierarchy, mapping, and offboarding
remain correct after retries, failures, permission changes, provider
differences, and service restarts.

# Reconciliation model

Create:

```text
iam.provisioning_jobs
iam.provisioning_operations
iam.provisioning_checkpoints
iam.reconciliation_runs
iam.reconciliation_findings
iam.entitlement_snapshots
iam.scim_event_feeds
iam.scim_event_deliveries
iam.scim_event_receipts
