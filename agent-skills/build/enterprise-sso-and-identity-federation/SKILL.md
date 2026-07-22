---
name: enterprise-sso-and-identity-federation
description: Build or review ELMOS enterprise OIDC and SAML federation, domain verification, subject mapping, group synchronization, assurance, sessions, logout, and emergency local access. Use for any login, identity-provider, membership, or high-risk reauthentication work.
---

# Enterprise Sso And Identity Federation

## Boundary

This is an ELMOS Build Skill. Use it to develop or review the ELMOS product itself, never to authorize migration of a customer repository. Preserve organization, actor, policy version, correlation, immutable input and evidence identities. Missing configuration, evidence or authority is a blocking result rather than success.

## Required rules

- Prefer OIDC Authorization Code plus PKCE and use maintained Spring Security protocol support; also support SAML through a replaceable adapter.
- Validate issuer, audience, signature, expiry, state and nonce; validate SAML recipient, audience, InResponseTo and replay protection.
- Key identities by provider connection plus provider subject, never email; unknown groups grant no elevated role.
- Keep client secrets as Secret References and make break-glass disabled, time-bound, dual-controlled and fully audited.

## Implementation workflow

1. Read the affected ADRs, contracts, persistence migration, module boundary and current tests.
2. Identify the data owner, tenant boundary, identity, authorization decision, external side effects and rollback path.
3. Implement a framework-free domain policy first, then expose it through a narrow application adapter.
4. Persist stable identities, organization scope, idempotency keys, policy versions, hashes and explicit status.
5. Add negative tests for forgery, cross-tenant access, replay, missing evidence, concurrency and stale decisions as applicable.
6. Keep external providers behind ports and return NOT_CONFIGURED, BLOCKED, NOT_RUN or INCONCLUSIVE until real evidence exists.
7. Run focused tests, architecture rules, database migration verification and the repository-wide build.

## Required tests

- Reject issuer, audience, nonce and unsigned-token failures.
- Verify domain ownership before JIT provisioning and revoke roles when external groups disappear.
- Keep local and provider logout/session revocation observable.

## Evidence and acceptance

Return affected files, policy decisions, commands, test results, skipped live integrations and remaining gates. Do not claim an IdP, Runner, Vault, model, payment, SCM, accounting, SIEM or offline environment is working from a unit test or configuration plan alone.

