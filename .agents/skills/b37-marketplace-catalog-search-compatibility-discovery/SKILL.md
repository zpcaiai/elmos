---
name: b37-marketplace-catalog-search-compatibility-discovery
description: Implement marketplace catalog indexing search filtering compatibility discovery version comparison documentation preview and safe recommendation eligibility.
---

# Skill B37-X03: b37-marketplace-catalog-search-compatibility-discovery

## Use this skill when

- The Batch 37 extension ecosystem requires this lifecycle capability to be production-complete and independently testable.
- A Codex implementation task must create typed contracts, deterministic workflows, evidence, and conservative gates rather than prose-only policy.

## Domain-specific risks and invariants

- Search ranking never overrides compatibility, security, tenant policy, or revocation.
- Display names are not unique identities; publisher and immutable extension IDs are authoritative.
- Paid placement is visually and machine-readably disclosed.

## Workflow

1. Define canonical catalog entry fields for identity, publisher, release digest, certification, permissions, compatibility, support, regions, pricing, and documentation.
2. Index only certified or explicitly allowed preview releases and bind every entry to immutable release metadata.
3. Implement search, filters, exact compatibility checks, version comparison, and tenant-policy-aware discovery.
4. Prevent revoked, incompatible, region-blocked, or untrusted releases from appearing as installable.
5. Test stale index, alias collision, typo-squatting, revoked release, and incompatible product-version scenarios.

## Required repository outputs

- `catalog/catalog-entry.json`
- search index contract, compatibility discovery evidence, and version comparison output

## Verification

- Run `validate_catalog_governance.py`.
- Query representative catalogs and prove incompatible or revoked releases cannot be recommended or installed.

## Stop and escalate when

- Catalog identity conflicts or stale revocation data exist.
- Compatibility cannot be computed from exact product, SDK, edition, region, and permission facts.

## Definition of done

- Catalog entries are immutable-release-backed, compatibility-aware, searchable, and safe under negative discovery tests.
