---
name: elmos-fde-git-history-ownership-change-coupling
description: Repository-owned bounded FDE capability handler for git-history-ownership-change-coupling; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 03-semantic-intelligence
  source_id: git-history-ownership-change-coupling
  alias: elmos-fde-git-history-ownership-change-coupling
  handler: elmos_fde_delivery.handlers.semantic:execute_git_history_ownership_change_coupling
  dependencies:
  - repository-custody-and-revisionset
  - asset-inventory-and-classification
  effect_boundary: E3
  routable: false
---

# elmos-fde-git-history-ownership-change-coupling

This skill provides the repository-owned bounded implementation for `git-history-ownership-change-coupling` in pack `03-semantic-intelligence`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
