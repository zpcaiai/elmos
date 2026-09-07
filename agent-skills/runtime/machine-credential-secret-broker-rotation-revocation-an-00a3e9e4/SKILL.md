---
name: machine-credential-secret-broker-rotation-revocation-an-00a3e9e4
description: "Inventory and govern machine credentials through secret references, short-lived leases, rotation, revocation, introspection, usage tracking, compromise status, and migration from static shared secrets."
---

# Objective

Replace unmanaged machine secrets with a governed credential lifecycle:

register secret reference
→ approve purpose and scope
→ issue short-lived lease
→ inject only into target workload
→ observe use
→ rotate
→ revoke
→ verify removal

ELMOS is a broker and governance layer, not a replacement for a production
secret manager.

# Provider abstraction

```java
public interface SecretProvider {
    SecretProviderType type();

    SecretLease lease(SecretLeaseRequest request);

    RotationResult rotate(SecretReference reference);

    RevocationResult revoke(SecretReference reference);

    SecretMetadata metadata(SecretReference reference);
}
