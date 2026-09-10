---
name: database-schema-routine-data-transformation
description: Repository-owned bounded FDE capability handler for database-schema-routine-data-transformation; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: database-schema-routine-data-transformation
  alias: database-schema-routine-data-transformation
  handler: elmos_fde_delivery.handlers.transformation:execute_database_schema_routine_data_transformation
  dependencies:
  - proof-guided-atomic-refactor-execution
  - data-database-migration-audit
  - business-invariant-recovery
  effect_boundary: E3
  routable: false
---

# database-schema-routine-data-transformation

This skill provides the repository-owned bounded implementation for `database-schema-routine-data-transformation` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
