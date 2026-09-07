---
name: authentication-scheme-migrator
description: "Migrate cookie, session, JWT, OAuth2, OIDC, API key, Basic, certificate, principal, challenge, and logout behavior. Use for framework authentication conversion."
---
# Authentication Scheme Migrator
Read `../references/afsm-v1.md`. Preserve credential source, token verification, issuer, audience, algorithm, clock skew, claims/principal, cookie/session/CSRF properties, challenge, forbid, anonymous and external-provider flows.

Place authentication before authorization and preserve 401 versus 403. Emit secret references only; never copy passwords, signing keys, client secrets or MFA material. Block decode-without-verify, missing issuer/audience or unreviewed flow changes.

