---
name: saml-scim-organization-lifecycle-orchestrator
description: "Implement Batch 34B end to end: SAML enterprise login, SCIM user/group provisioning, organization hierarchy, group-to-role mapping, deprovisioning, reconciliation, and release gates."
---

# Objective

Implement this enterprise identity lifecycle:

SAML identity provider
→ SAML login
→ federated identity
→ tenant and organization membership
→ SCIM user/group provisioning
→ approved entitlement mapping
→ resource access
→ deactivation
→ access revocation and ownership transfer
→ reconciliation

# Preconditions

Before changing code, verify Batch 34A provides:

- verified OIDC authentication;
- FederatedIdentity;
- Tenant;
- TenantMembership;
- Role and Permission;
- ResourceGrant;
- TenantContext;
- PostgreSQL RLS;
- AuthorizationService;
- audit events;
- identity-security-gate.

If any precondition is absent, document the gap and implement only the
minimum safe prerequisite. Do not create a parallel identity model.

# Preflight inventory

Search for:

- SAML;
- saml2Login;
- RelyingPartyRegistration;
- SCIM;
- externalId;
- userName;
- group claim;
- email-based identity linking;
- physical identity deletes;
- membership revoke;
- session revoke;
- API token revoke;
- owner_id;
- organization_unit;
- parent_id;
- SCIM or directory secrets.

Write:

docs/security/batch-34b-baseline.md

The document must include:

- current identity model;
- current membership model;
- current group/role behavior;
- current session and token revocation paths;
- current ownership-bearing resources;
- current physical delete behavior;
- current protocol exposure.

# Implementation order

## Phase 1: shared domain and schema

Add:

- SamlConnection;
- SamlConnectionVersion;
- ScimConnection;
- ProvisionedIdentity;
- ExternalGroup;
- ExternalGroupMember;
- GroupEntitlementMapping;
- OrganizationUnit;
- OrganizationClosure;
- DelegatedAdministrationScope;
- OffboardingCase;
- ProvisioningOperation;
- ReconciliationRun.

## Phase 2: SAML

Implement persistent multi-tenant SAML relying-party registrations,
metadata handling, login exchange, replay protection, local logout, optional
SLO, and certificate rotation.

## Phase 3: SCIM core

Implement authenticated SCIM 2.0 Users, Groups, schema discovery, standard
errors, and tenant-bound service-provider connections.

## Phase 4: advanced SCIM

Implement filters, PATCH, ETags, pagination, bounded bulk, idempotency, and
optional cursor pagination.

## Phase 5: organization and entitlement mapping

Implement organization hierarchy, delegated administration, external group
mapping, JIT policy, source authority, and impact preview.

## Phase 6: offboarding

Implement deactivation and deletion cascades using transaction + outbox +
reconciliation.

## Phase 7: verification

Add protocol, tenant, escalation, deprovisioning, and recovery tests.

# Required logical commits

1. saml-scim-domain-and-schema
2. saml-relying-party-login-and-metadata
3. scim-users-groups-and-discovery
4. scim-patch-filter-etag-and-pagination
5. organization-hierarchy-and-group-mapping
6. offboarding-and-access-revocation
7. reconciliation-events-tests-and-docs

# Hard stop conditions

Stop and report BLOCKED when:

- Batch 34A tenant isolation is not functioning;
- SAML login would require trusting email as the only stable identity key;
- a SAML connection cannot be unambiguously bound to one tenant;
- SCIM client authentication cannot be bound to one tenant;
- existing identity deletion would destroy mandatory audit evidence;
- privileged external groups are already mapped directly to admin roles and
  cannot be migrated safely;
- the current schema cannot represent identity source authority;
- access revocation has no reliable session or credential invalidation path.

# Completion definition

Batch 34B is complete only when:

- one tenant can configure multiple SAML connections;
- SAML assertion replay is blocked;
- SAML attributes do not directly create privileged roles;
- a SCIM client is bound to one tenant and connection;
- Users and Groups endpoints are interoperable;
- active=false removes effective access;
- group-to-role mappings are versioned and approved;
- organization hierarchy is cycle-free;
- delegated administration is subtree-limited;
- offboarding revokes effective access and identifies ownership transfer;
- provisioning drift is detectable;
- all protocol and negative tests pass.

# Completion report

Return:

1. federation architecture;
2. SAML connection lifecycle;
3. SCIM capability matrix;
4. organization hierarchy;
5. group mapping and JIT policy;
6. offboarding cascade;
7. reconciliation behavior;
8. exact commands and results;
9. files and migrations changed;
10. remaining provider-specific limitations.
