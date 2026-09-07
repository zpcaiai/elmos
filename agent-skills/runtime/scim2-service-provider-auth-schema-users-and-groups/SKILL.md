---
name: scim2-service-provider-auth-schema-users-and-groups
description: "Implement a tenant-bound SCIM 2.0 service provider with authenticated clients, discovery endpoints, Users, Groups, standard schemas, errors, and provisioning audit."
---

# Objective

Expose ELMOS as a SCIM 2.0 service provider for enterprise directory
provisioning.

Each SCIM connection belongs to exactly one ELMOS tenant and provisioning
scope.

# Base URI

Use a non-guessable provisioning connection ID:

```text
/scim/v2/{connectionId}
