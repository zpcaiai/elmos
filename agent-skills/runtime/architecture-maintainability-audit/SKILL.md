---
name: architecture-maintainability-audit
description: Repository-owned bounded FDE capability handler for architecture-maintainability-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: architecture-maintainability-audit
  alias: architecture-maintainability-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_architecture_maintainability_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - business-capability-code-mapping
  - git-history-ownership-change-coupling
  effect_boundary: E3
  routable: false
---

# architecture-maintainability-audit

This skill provides the repository-owned bounded implementation for `architecture-maintainability-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
