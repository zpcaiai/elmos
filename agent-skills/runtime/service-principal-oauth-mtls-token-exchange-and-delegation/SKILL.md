---
name: service-principal-oauth-mtls-token-exchange-and-delegation
description: "Implement service principals, OAuth machine-client authentication, mTLS/private-key clients, token exchange, delegation chains, scope narrowing, audience restriction, and proof-of-possession validation."
---

# Objective

Allow authenticated workloads to obtain short-lived, narrowly scoped
downstream authority without sharing user or service credentials.

Target flow:

incoming human or workload authority
→ authenticated calling workload
→ token exchange policy
→ short-lived downstream token
→ audience-bound resource access
→ actor and delegation audit

# Architecture boundary

ELMOS should normally integrate with an approved authorization server.

Create provider interfaces:

```java
public interface MachineAuthorizationProvider {
    MachineTokenResult clientCredentials(
        MachineClientRequest request
    );

    MachineTokenResult exchange(
        TokenExchangeRequest request
    );

    TokenStatus introspect(
        TokenReference token
    );

    void revoke(
        TokenReference token,
        String reason
    );
}
