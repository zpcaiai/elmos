---
name: deprovision-offboarding-session-token-ownership-and-acc-95f874ef
description: "Implement immediate access suspension and durable offboarding cascades for SCIM deactivation/delete, membership revocation, session/token invalidation, ownership transfer, reconciliation, and reactivation."
---

# Objective

Make deprovisioning fast, durable, idempotent, and auditable.

A SCIM `active=false` or approved membership revocation must stop effective
access quickly without deleting required identity or audit history.

# Trigger types

SCIM_ACTIVE_FALSE
SCIM_DELETE
MEMBERSHIP_REVOKED
MEMBERSHIP_EXPIRED
DIRECTORY_EVENT
CONTRACT_EXPIRED
TENANT_ADMIN_ACTION
SECURITY_INCIDENT

# Offboarding aggregate

Create:

```text
iam.offboarding_cases
iam.offboarding_steps
iam.offboarding_impacted_resources
iam.offboarding_ownership_transfers
iam.credential_revocation_jobs
iam.session_revocation_jobs
iam.offboarding_reconciliations
iam.identity_tombstones
