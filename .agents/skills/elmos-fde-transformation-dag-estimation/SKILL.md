---
name: elmos-fde-transformation-dag-estimation
description: Repository-owned bounded FDE capability handler for transformation-dag-estimation; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: transformation-dag-estimation
  alias: elmos-fde-transformation-dag-estimation
  handler: elmos_fde_delivery.handlers.transformation:execute_transformation_dag_estimation
  dependencies:
  - target-architecture-alternatives-and-adr
  effect_boundary: E3
  routable: false
---

# elmos-fde-transformation-dag-estimation

This skill provides the repository-owned bounded implementation for `transformation-dag-estimation` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
