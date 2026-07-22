---
name: b37-publisher-onboarding-identity
description: "Implement publisher onboarding identity verification organization membership agreements payout tax security contacts signing identities and lifecycle governance."
---

# Skill 1320: b37-publisher-onboarding-identity

## Use this skill when

- External or internal publishers need marketplace access.
- Publisher identity is currently an unverified account name.

## Domain-specific risks and invariants

- Anonymous or weakly verified publishers increase supply-chain and payment risk.
- Shared credentials obscure accountability.

## Workflow

1. Define publisher types, identity proofing, organization ownership, authorized maintainers, security contacts, agreements, tax/payout, support, and data-processing requirements.
2. Implement individual identities, MFA, least-privilege roles, signing identity binding, and maintainer changes.
3. Add sanctions, fraud, conflict, and duplicate-organization review hooks where legally required.
4. Test compromised maintainer, departed employee, organization transfer, and emergency freeze.
5. Maintain immutable onboarding and status history.

## Required repository outputs

- publisher profile and verification evidence
- role and signing-identity assignments
- agreements payout support and lifecycle records

## Verification

- Verify every maintainer has an individual identity and MFA.
- Verify departed or suspended maintainers lose publish and signing rights.
- Test organization transfer and emergency freeze.

## Stop and escalate when

- Publisher ownership or legal rights are disputed.
- Required agreements, security contact, or payout identity is incomplete.

## Definition of done

- Only verified authorized publishers can submit releases.
- Publisher changes are auditable and revocable.
