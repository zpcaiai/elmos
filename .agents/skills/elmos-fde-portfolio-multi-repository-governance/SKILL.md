---
name: elmos-fde-portfolio-multi-repository-governance
description: Repository-owned bounded FDE capability handler for portfolio-multi-repository-governance; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 06-verification-release-operations
  source_id: portfolio-multi-repository-governance
  alias: elmos-fde-portfolio-multi-repository-governance
  handler: elmos_fde_delivery.handlers.operations:execute_portfolio_multi_repository_governance
  dependencies:
  - reusable-recipe-skill-learning
  - support-profile-and-unknown-register
  effect_boundary: E3
  routable: false
---

# elmos-fde-portfolio-multi-repository-governance

This skill provides the repository-owned bounded implementation for `portfolio-multi-repository-governance` in pack `06-verification-release-operations`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
