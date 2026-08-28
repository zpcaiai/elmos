# Implementation Guide — Template Marketplace and Package Lifecycle Governor

## Purpose

Govern reusable templates, Skills, adapters and archetypes through publisher identity, compatibility, signing, review, distribution, update and revocation.

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

1. register package identity and capabilities
2. verify signatures, provenance and licenses
3. run compatibility and malicious-package tests
4. stage rollout and tenant policy filtering
5. revoke and replace compromised packages

## Native acceptance corpus

- `ELMOS_TEMPLATE_MARKETPLACE_PACKAGE_LIFECYCLE_GOVERNOR-01` — native scenario: register package identity and capabilities
- `ELMOS_TEMPLATE_MARKETPLACE_PACKAGE_LIFECYCLE_GOVERNOR-02` — native scenario: verify signatures, provenance and licenses
- `ELMOS_TEMPLATE_MARKETPLACE_PACKAGE_LIFECYCLE_GOVERNOR-03` — native scenario: run compatibility and malicious-package tests
- `ELMOS_TEMPLATE_MARKETPLACE_PACKAGE_LIFECYCLE_GOVERNOR-04` — native scenario: stage rollout and tenant policy filtering
- `ELMOS_TEMPLATE_MARKETPLACE_PACKAGE_LIFECYCLE_GOVERNOR-05` — native scenario: revoke and replace compromised packages

## Production implementation rule

Do not mark this Skill implemented from this package alone. Replace all release-time placeholders, integrate real services and target-native tools, run the acceptance corpus, seal current evidence and obtain an independent certificate for the exact RevisionSet.
