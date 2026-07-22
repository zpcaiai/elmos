---
name: scim-user-group-provisioning
description: Govern tenant-scoped SCIM Users, Groups, enterprise extensions, role mappings, retries, and deprovisioning. Use for automated identity lifecycle provisioning and SCIM conformance.
---

# SCIM User Group Provisioning

Read `../references/batch-12-enterprise-platform.md`. Bind each SCIM client to one tenant, keep external IDs unique within it, allowlist group-to-role mappings and make create/update/deprovision idempotent. Disable sessions and tokens immediately while retaining Artifacts under policy.

SCIM cannot grant Platform Super Admin. Cross-tenant provisioning or an active deprovisioned user blocks T-A.
