---
name: cross-language-framework-transformation
description: Repository-owned bounded FDE capability handler for cross-language-framework-transformation; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: cross-language-framework-transformation
  alias: cross-language-framework-transformation
  handler: elmos_fde_delivery.handlers.transformation:execute_cross_language_framework_transformation
  dependencies:
  - proof-guided-atomic-refactor-execution
  - business-invariant-recovery
  effect_boundary: E3
  routable: false
---

# cross-language-framework-transformation

This skill provides the repository-owned bounded implementation for `cross-language-framework-transformation` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
