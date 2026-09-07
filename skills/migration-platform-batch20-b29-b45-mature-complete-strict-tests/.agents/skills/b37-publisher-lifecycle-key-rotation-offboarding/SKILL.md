---
name: b37-publisher-lifecycle-key-rotation-offboarding
description: Implement publisher re-verification maintainer lifecycle signing-key rotation ownership transfer suspension offboarding succession and orphan-extension governance.
---

# Skill B37-X05: b37-publisher-lifecycle-key-rotation-offboarding

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Shared publisher accounts and unowned signing keys are prohibited.
- Ownership transfer never transfers customer data or tenant access automatically.
- Offboarding revokes publish rights before payout or legal records are archived.

## Workflow

1. Inventory legal entity, organization owners, maintainers, security contacts, signing identities, agreements, payout status, and published releases.
2. Implement periodic re-verification and immediate review on legal, ownership, security-contact, or sanction changes.
3. Implement signing-key generation, overlap rotation, expiry, compromise revocation, and emergency replacement.
4. Implement maintainer departure, organization transfer, merger/acquisition, suspension, offboarding, and orphan-extension succession.
5. Notify affected tenants and preserve release, certification, payout, legal, and audit records.

## Required repository outputs

- `publishers/lifecycle.json`
- key-rotation evidence, ownership-transfer records, offboarding plan, and orphan-extension decisions

## Verification

- Run `validate_publisher_lifecycle.py`.
- Exercise routine rotation, compromised-key revocation, maintainer departure, and publisher suspension.

## Stop and escalate when

- No verified replacement security contact or owner exists.
- A key compromise cannot be bounded to exact releases and tenants.

## Definition of done

- Publisher identity, keys, maintainers, transfer, suspension, and offboarding are continuously governed.
