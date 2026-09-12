---
name: elmos-fde-data-database-migration-audit
description: Repository-owned bounded FDE capability handler for data-database-migration-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: data-database-migration-audit
  alias: elmos-fde-data-database-migration-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_data_database_migration_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - data-event-permission-lineage
  effect_boundary: E3
  routable: false
---

# elmos-fde-data-database-migration-audit

This skill provides the repository-owned bounded implementation for `data-database-migration-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
