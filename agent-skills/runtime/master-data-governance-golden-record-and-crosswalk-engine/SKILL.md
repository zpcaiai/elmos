---
name: master-data-governance-golden-record-and-crosswalk-engine
description: Govern enterprise master data ownership, matching, Golden Records, field-level survivorship, hierarchies, merges, splits, redirects, tombstones, and ID Crosswalks. Use for customer, supplier, product, employee, organization, account, location, asset, or contract migration.
---

# Master Data Governance

## Execute

1. Assign a Business Owner and classify each source as authoritative, trusted, reference, enrichment, legacy, or unknown.
2. Version exact-ID, normalized-name, address, tax-ID, email, phone, fuzzy, domain, and manual match rules.
3. Preserve `MATCH`, `POSSIBLE_MATCH`, `NO_MATCH`, `CONFLICT`, and `MANUAL_REVIEW` separately.
4. Define Golden Records as approved field-level authority and provenance, not a union of every source field.
5. Apply field-level survivorship by preferred source, recency, quality, business priority, or approved manual override.
6. Version Crosswalk source and target IDs, validity, merge, split, redirect, and tombstone history.
7. Validate legal-entity, customer, sales, product, organization, and cost-center hierarchies.

## Hard gates

Never auto-merge `POSSIBLE_MATCH`. Block transaction migration while required master-data ownership, quality, hierarchy, or Crosswalk is unresolved.
