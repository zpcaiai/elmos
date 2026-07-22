---
name: tenant-membership-current-tenant-and-lifecycle
description: "Implement tenant, federated identity, membership, role assignment, current-tenant selection, suspension, and lifecycle APIs."
---

# Objective

Implement a persistent tenant membership model:

verified federated identity
→ internal identity
→ active tenant membership
→ role assignments
→ current tenant candidate validation
→ TenantContext

# Domain model

Create or adapt the following domain types.

```java
public record IdentityId(UUID value) {}

public record TenantId(UUID value) {}

public record MembershipId(UUID value) {}

public enum MembershipStatus {
    INVITED,
    ACTIVE,
    SUSPENDED,
    EXPIRING,
    EXPIRED,
    REVOKED
}

public record TenantContext(
    TenantId tenantId,
    IdentityId identityId,
    MembershipId membershipId,
    Set<String> roleCodes,
    String requestId
) {}
