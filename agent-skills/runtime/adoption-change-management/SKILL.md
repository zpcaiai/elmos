---
name: adoption-change-management
description: Repository-owned bounded FDE capability handler for adoption-change-management; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 01-fde-engagement
  source_id: adoption-change-management
  alias: adoption-change-management
  handler: elmos_fde_delivery.handlers.engagement:execute_adoption_change_management
  dependencies:
  - pilot-scope-sow-acceptance
  effect_boundary: E3
  routable: false
---

# adoption-change-management

This skill provides the repository-owned bounded implementation for `adoption-change-management` in pack `01-fde-engagement`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
