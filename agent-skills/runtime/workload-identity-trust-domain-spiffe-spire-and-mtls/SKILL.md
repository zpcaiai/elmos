---
name: workload-identity-trust-domain-spiffe-spire-and-mtls
description: "Implement provider-neutral workload identity, trust domains, SPIFFE/SPIRE integration, mTLS peer authentication, registration, attestation, rotation, revocation, and authorization."
---

# Objective

Replace implicit network trust and shared internal API keys with distinct,
short-lived, verifiable workload identities.

Target subjects:

- control-api;
- workflow-worker;
- agent-gateway;
- report-worker;
- graph-projector;
- runner-gateway;
- private-runner;
- sandbox task candidate;
- CLI automation candidate.

# Provider abstraction

Create:

```java
public interface WorkloadIdentityProvider {
    WorkloadIdentityProviderType type();

    WorkloadIdentityRegistration register(
        WorkloadRegistrationRequest request
    );

    WorkloadIdentityStatus status(WorkloadIdentityId id);

    void rotate(WorkloadIdentityId id);

    void revoke(WorkloadIdentityId id, String reason);

    WorkloadPeerVerification verify(WorkloadPeerEvidence evidence);
}
