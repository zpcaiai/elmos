---
name: enterprise-sso-and-identity-federation
description: Validate tenant-bound OIDC and SAML federation, discovery, routing, claim mapping, JIT provisioning, logout, and key rotation. Use for enterprise SSO onboarding or identity security assessment.
---

# Enterprise SSO and Identity Federation

Read `../references/batch-12-enterprise-platform.md`. For OIDC verify code flow, PKCE, state, nonce, issuer, audience, signature and expiry; for SAML verify signatures, audience, recipient, response binding, replay and certificate rotation. Bind each IdP and stable external subject to one tenant.

Never trust an unverified email or grant Admin through JIT. Wrong-tenant identity or decode-without-verify blocks T-A.
