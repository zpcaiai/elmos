---
name: b37-enterprise-private-marketplace-allowlist-promotion
description: Implement customer private marketplaces publisher and extension allowlists internal publishing approval staged promotion and tenant-isolated governance.
---

# Skill B37-X11: b37-enterprise-private-marketplace-allowlist-promotion

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Public certification is not sufficient for tenant allowlisting.
- Private extensions remain private unless explicitly re-published through a separate reviewed release.
- Promotion never rebuilds or changes the artifact digest.

## Workflow

1. Define tenant-private catalog, trusted publishers, allowed extension kinds, permissions, regions, models, data classes, and approval policies.
2. Support customer-private extensions that never enter the public catalog.
3. Implement promotion from development to test to production using immutable digests and environment-specific approvals.
4. Prevent cross-tenant discovery, installation, evidence, billing, and publisher-access leakage.
5. Reconcile private catalog, installations, policy, and revocation state.

## Required repository outputs

- `private-marketplace/policy.json`
- allowlists, promotion records, private publisher records, tenant audit, and reconciliation evidence

## Verification

- Run `validate_private_marketplace.py`.
- Prove cross-tenant access, unauthorized publisher, permission expansion, and promotion-bypass attempts fail.

## Stop and escalate when

- Tenant ownership, data boundary, or approval authority is missing.
- Private extension artifacts cannot be cryptographically separated from public artifacts.

## Definition of done

- Private marketplace discovery, publishing, promotion, installation, audit, and revocation are tenant-isolated and reconciled.
