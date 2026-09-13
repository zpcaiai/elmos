---
name: product-feedback-roadmap-loop
description: Repository-owned bounded FDE capability handler for product-feedback-roadmap-loop; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 06-verification-release-operations
  source_id: product-feedback-roadmap-loop
  alias: product-feedback-roadmap-loop
  handler: elmos_fde_delivery.handlers.operations:execute_product_feedback_roadmap_loop
  dependencies:
  - status-risk-decision-communications
  - adoption-change-management
  - reusable-recipe-skill-learning
  effect_boundary: E3
  routable: false
---

# product-feedback-roadmap-loop

This skill provides the repository-owned bounded implementation for `product-feedback-roadmap-loop` in pack `06-verification-release-operations`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
