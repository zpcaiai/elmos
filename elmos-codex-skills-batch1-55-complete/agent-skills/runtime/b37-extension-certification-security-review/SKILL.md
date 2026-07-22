---
name: b37-extension-certification-security-review
description: "Implement technical certification security privacy performance compatibility documentation support and domain review workflows for extension releases."
---

# Skill 1321: b37-extension-certification-security-review

## Use this skill when

- An extension release is ready for marketplace review.
- Different extension kinds need consistent but risk-based certification.

## Domain-specific risks and invariants

- A checklist-only review can miss runtime abuse or semantic corruption.
- Sales or publisher pressure can bypass unresolved critical findings.

## Workflow

1. Classify extension kind, permissions, data exposure, side effects, business criticality, and risk tier.
2. Select required automated and human reviews.
3. Run build, SDK conformance, sandbox, negative, holdout, performance, privacy, security, compatibility, documentation, and support checks.
4. Record findings, remediation, reviewer independence, waivers, and expiration.
5. Issue bounded certification tied to exact artifact digest and product versions.

## Required repository outputs

- certification profile, findings, approvals, and evidence
- risk-based review workflow
- certification badge scope and expiry

## Verification

- Verify certification references the exact signed release.
- Run independent holdout and adversarial tests.
- Verify critical waivers cannot be self-approved.

## Stop and escalate when

- Critical security privacy semantic or supply-chain finding is open.
- Reviewer independence or domain expertise is insufficient.

## Definition of done

- Certification is exact, scoped, expiring, and reproducible.
- No critical finding or unknown remains.
