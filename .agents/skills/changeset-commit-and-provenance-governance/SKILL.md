---
name: changeset-commit-and-provenance-governance
description: Repository-owned bounded FDE capability handler for changeset-commit-and-provenance-governance; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: changeset-commit-and-provenance-governance
  alias: changeset-commit-and-provenance-governance
  handler: elmos_fde_delivery.handlers.transformation:execute_changeset_commit_and_provenance_governance
  dependencies:
  - transformation-dag-estimation
  effect_boundary: E3
  routable: false
---

# changeset-commit-and-provenance-governance

This skill provides the repository-owned bounded implementation for `changeset-commit-and-provenance-governance` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
