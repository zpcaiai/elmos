---
name: workload-privileged-access-review-orchestrator
description: "Implement Batch 34C end to end: workload identities, mTLS, OAuth delegation, machine credential lifecycle, JIT privileged access, break-glass, access reviews, and credential incident response."
---

# Objective

Implement this security chain:

service / runner / agent starts
→ workload attestation
→ short-lived workload identity
→ mTLS service authentication
→ contextual authorization
→ delegated downstream token when needed
→ JIT privileged grant for exceptional human operations
→ access review
→ revocation and incident recovery

# Preconditions

Verify Batch 34A provides:

- human authentication;
- TenantContext;
- RBAC/ABAC;
- ResourceGrant;
- session revocation;
- PostgreSQL RLS;
- authorization audit.

Verify Batch 34B provides:

- SAML/SCIM identity lifecycle;
- organization hierarchy;
- offboarding;
- entitlement source;
- reconciliation infrastructure.

Do not create a parallel role, grant, tenant, session, or audit model.

# Preflight inventory

Search for:

- X-Internal-Service;
- X-Forwarded-Client-Cert;
- X-Runner-Id;
- internal API key;
- shared secret;
- client_secret;
- static token;
- runner token;
- service account;
- mTLS;
- certificate;
- SPIFFE;
- SPIRE;
- Vault;
- OAuth client credentials;
- token exchange;
- admin bypass;
- super admin;
- break glass;
- access review;
- revoke;
- introspect;
- secret environment variables.

Write:

docs/security/batch-34c-baseline.md

The inventory must classify every machine credential by:

- owner;
- tenant;
- service;
- storage;
- lifetime;
- rotation;
- revocation;
- observed use;
- target replacement.

# Implementation order

## Phase 1: common domain

Add:

- TrustDomain;
- WorkloadIdentity;
- WorkloadRegistration;
- WorkloadAttestation;
- ServicePrincipal;
- MachineCredential;
- Delegation;
- DelegatedTokenRecord;
- PrivilegedAccessRequest;
- PrivilegedGrant;
- BreakGlassSession;
- AccessReviewCampaign;
- AccessReviewItem;
- IdentitySecurityIncident.

## Phase 2: workload identity

Implement provider abstraction, native development mTLS provider, and
SPIFFE/SPIRE adapter.

## Phase 3: OAuth machine authorization

Implement service principals, mTLS/private-key client authentication,
token-exchange adapter, delegation constraints, and token status adapters.

## Phase 4: credential broker

Implement secret references, short-lived leases, rotation, revocation,
introspection, and compromise status.

## Phase 5: privileged access

Implement JIT request, approval, activation, expiry, revocation, and audit.

## Phase 6: break-glass

Implement emergency access, dual control, alerts, restricted sessions,
automatic revocation, and post-use review.

## Phase 7: access review

Implement entitlement snapshots, reviewer assignment, certification,
remediation, and verification.

## Phase 8: incidents and gates

Implement credential compromise containment, drills, negative tests,
recovery tests, and mandatory CI evidence.

# Required logical commits

1. workload-identity-domain-and-schema
2. spiffe-mtls-and-service-authentication
3. service-principal-token-exchange-and-delegation
4. credential-broker-rotation-and-revocation
5. jit-privileged-access
6. break-glass-emergency-access
7. access-review-and-remediation
8. credential-incident-tests-and-docs

# Hard stop conditions

Stop and report BLOCKED when:

- internal services cannot distinguish authenticated peer identity;
- the deployment terminates TLS before ELMOS with no trustworthy peer
  identity propagation contract;
- current shared machine credentials cannot be inventoried;
- no supported secret store or workload identity provider exists for
  production deployment;
- privileged grants cannot be invalidated without restarting services;
- authorization caches cannot observe revocation;
- access-review decisions cannot be mapped to actual effective grants;
- break-glass activity cannot be audited;
- implementing token exchange would require ELMOS to issue unrestricted
  impersonation tokens.

# Completion definition

Batch 34C is complete only when:

- every production workload has a distinct identity;
- service-to-service access is authenticated and resource-authorized;
- delegated authority is narrower than incoming authority;
- machine credentials are short-lived or have managed rotation;
- JIT grants expire automatically;
- break-glass is constrained, alerted, revoked, and reviewed;
- access reviews include machine and derived entitlements;
- remediation decisions are executed and verified;
- credential compromise can trigger bulk containment;
- all security and recovery tests pass.

# Completion report

Return:

1. trust-domain topology;
2. workload identity providers;
3. machine credential inventory and migration;
4. token delegation flow;
5. JIT flow;
6. break-glass flow;
7. access-review coverage;
8. incident containment flow;
9. exact commands and results;
10. migrations and files changed;
11. unresolved provider limitations.
