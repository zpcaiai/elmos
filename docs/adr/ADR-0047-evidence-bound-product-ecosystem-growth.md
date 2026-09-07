# ADR-0047: Evidence-bound Product and Ecosystem Growth Model

- Status: Accepted
- Date: 2026-07-21

## Context

Batch 14 defines a unified growth system spanning product-led activation, content, developer experience, community, Marketplace, internationalization, regional expansion, economics and trust. These capabilities depend on external identity, analytics, content, community, payment, legal, tax, support and partner authorities. Repository code cannot truthfully claim their operational outcomes.

The complete specification defines Skills 401–460, PEGM seven value domains, five measured flywheels and non-compensating gates G14-A through G14-G.

## Decision

Implement `modules/ecosystem-growth` as an evidence-only PEGM adjudicator.

- Require immutable signed B13-G provenance.
- Require a versioned, quality-gated Monthly Verified Migration Value definition.
- Require all seven PEGM domains: Acquisition, Activation, Adoption, Retention, Expansion, Advocacy and Ecosystem.
- Require the five product, content, community, Marketplace and regional flywheels.
- Observe six external assurance areas and one final conformance authority.
- Apply exact G14-A through G14-G controls sequentially and non-compensating.
- Permit `scalable_growth_ready=true` only at G14-G with complete evidence, visible CAC and contribution margin, all six supported motions and zero critical open growth risk.
- Keep every control-plane artifact at `external_operation_executed=false`.
- Persist only tenant-isolated, evidence-bound projections; leave commercial and field authority in existing systems of record.

## Consequences

The repository can deterministically reject incomplete, mismatched, cross-tenant, unsafe, unreviewed, fabricated or economically opaque growth claims. It cannot by itself establish real field acceptance. Skills 401–460 and the acceptance checklist retain that boundary explicitly.
