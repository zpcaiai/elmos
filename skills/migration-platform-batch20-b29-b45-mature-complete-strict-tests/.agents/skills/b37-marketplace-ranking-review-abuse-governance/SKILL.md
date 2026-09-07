---
name: b37-marketplace-ranking-review-abuse-governance
description: Implement transparent ranking verified reviews recommendation controls fraud detection moderation anti-abuse and publisher impersonation defenses.
---

# Skill B37-X04: b37-marketplace-ranking-review-abuse-governance

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Security and compatibility gates precede popularity or revenue signals.
- Individual customer source code, private usage, or sensitive telemetry is never used for public ranking.
- Moderation actions are auditable and appealable.

## Workflow

1. Define ranking features, prohibited signals, paid-placement disclosure, recommendation constraints, and human moderation responsibilities.
2. Require verified installation or purchase evidence for reviews and prevent publisher self-review or coordinated manipulation.
3. Detect review spam, ranking fraud, keyword stuffing, clone listings, trademark impersonation, and malicious update campaigns.
4. Provide appeal, correction, removal, and evidence-preservation workflows.
5. Run adversarial catalog, review, and recommendation tests.

## Required repository outputs

- `catalog/ranking-policy.json`
- review verification records, abuse cases, moderation decisions, and appeal evidence

## Verification

- Run `validate_catalog_governance.py`.
- Prove paid, popular, or highly rated but incompatible/revoked extensions remain blocked.

## Stop and escalate when

- Ranking logic can conceal sponsorship or bypass certification.
- Review identity or evidence provenance is unavailable.

## Definition of done

- Ranking is transparent, reviews are verified, abuse controls pass, and critical impersonation findings are zero.
