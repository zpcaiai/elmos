---
name: b37-marketplace-legal-takedown-export-appeal
description: "Implement copyright trademark patent license export-control sanctions regional restriction evidence preservation takedown and appeal governance."
---

# Skill B37-X09: b37-marketplace-legal-takedown-export-appeal

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Legal action scope is exact and does not delete evidence or customer-owned data.
- Security revocation and legal takedown are distinct but composable controls.
- No automated model makes the final legal decision.

## Workflow

1. Define legal case types, jurisdiction, owner, evidence requirements, decision authority, response clocks, and customer-impact rules.
2. Screen publishers, releases, regions, encryption, export classifications, sanctions, licenses, and restricted content.
3. Implement preservation, temporary restriction, takedown, delisting, execution block, payout hold, and customer notification.
4. Implement independent appeal, counter-evidence, restoration, remediation, and final disposition.
5. Test urgent injunction, counterfeit publisher, incompatible license, export restriction, and mistaken takedown scenarios.

## Required repository outputs

- `legal/legal-policy.json`
- case records, evidence holds, decisions, appeals, regional restrictions, and restoration evidence

## Verification

- Run `validate_legal_support.py`.
- Prove blocking, appeal, restoration, evidence preservation, and affected-customer notification.

## Stop and escalate when

- Jurisdiction, decision authority, or evidence-preservation duty is unresolved.
- A release must remain executable despite a binding restriction.

## Definition of done

- Legal, export, sanctions, takedown, and appeal paths are complete, auditable, and region-aware.
