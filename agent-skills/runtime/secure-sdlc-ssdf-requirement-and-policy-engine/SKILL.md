---
name: secure-sdlc-ssdf-requirement-and-policy-engine
description: Convert versioned SSDF, ASVS, threat, privacy, contract, incident, and organization inputs into scoped requirements and policy gates. Use throughout design, code, build, test, release, and operate stages.
---

# Secure SDLC Policy

1. Record each requirement's source catalog, source version, external identifier, scope, verification methods, owner, and lifecycle.
2. Derive gates for design, code, build, test, release, and operation from asset classification, exposure, profile, threats, and current controls.
3. Return explainable `ALLOW`, `DENY`, `REQUIRE_CONTROL`, `REQUIRE_TEST`, `REQUIRE_APPROVAL`, or `REQUIRE_EXCEPTION` decisions.
4. Require scope, reason, evidence, approver, review date, and version before marking a requirement not applicable.
5. Separate developer, security champion, security engineer, product/data owner, risk approver, and auditor duties.

## Acceptance

Keep catalogs versioned, treat draft standards as non-mandatory until approved, and never let a developer or agent bulk-waive requirements.
