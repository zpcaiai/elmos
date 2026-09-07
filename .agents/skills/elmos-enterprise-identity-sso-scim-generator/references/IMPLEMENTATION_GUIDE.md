# Implementation Guide — Enterprise Identity, SSO and SCIM Generator

## Purpose

Generate OIDC/SAML SSO, SCIM lifecycle, group/role mapping, session, MFA, service identity and break-glass integration.

## Required vertical slice

A conforming first implementation must execute one real, exact-version vertical slice through:

1. API command and idempotency validation;
2. PostgreSQL run/event/outbox persistence with tenant policy;
3. K7 authority, sandbox, lease and fencing acquisition;
4. the Skill-specific native operation;
5. at least one positive and one negative native fixture;
6. independent proof/evidence production;
7. K8 blocked-or-certified decision;
8. pause/resume and worker-loss recovery;
9. machine wall-clock and cost reporting;
10. safe uninstall/rollback or compensating action.

## Skill-specific work packages

1. integrate identity provider metadata and key rotation
2. map users/groups to tenant roles and policies
3. provision/deprovision through SCIM
4. enforce session/MFA and step-up
5. test orphaned access and emergency recovery

## Native acceptance corpus

- `ELMOS_ENTERPRISE_IDENTITY_SSO_SCIM_GENERATOR-01` — native scenario: integrate identity provider metadata and key rotation
- `ELMOS_ENTERPRISE_IDENTITY_SSO_SCIM_GENERATOR-02` — native scenario: map users/groups to tenant roles and policies
- `ELMOS_ENTERPRISE_IDENTITY_SSO_SCIM_GENERATOR-03` — native scenario: provision/deprovision through SCIM
- `ELMOS_ENTERPRISE_IDENTITY_SSO_SCIM_GENERATOR-04` — native scenario: enforce session/MFA and step-up
- `ELMOS_ENTERPRISE_IDENTITY_SSO_SCIM_GENERATOR-05` — native scenario: test orphaned access and emergency recovery

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
