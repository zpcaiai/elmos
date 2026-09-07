---
name: unified-scm-credential-webhook-event-git-transport-and-c2f4973f
description: "Implement unified provider credential leases, webhook normalization, Git operation contracts, repository access revocation, review-request delivery, commit-status publication, unknown-result reconciliation, and cross-provider audit."
---

# Objective

Prevent every provider adapter from inventing a separate security and
delivery path.

# Credential broker interface

```java
public interface ScmCredentialBroker {
    ScmCredentialLease issue(
        ScmCredentialLeaseRequest request
    );

    void revoke(
        ScmCredentialLeaseId leaseId,
        String reason
    );

    ScmCredentialLeaseStatus status(
        ScmCredentialLeaseId leaseId
    );
}
