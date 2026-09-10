---
name: elmos-fde-issue-ontology-and-finding-normalization
description: Repository-owned bounded FDE capability handler for issue-ontology-and-finding-normalization; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: issue-ontology-and-finding-normalization
  alias: elmos-fde-issue-ontology-and-finding-normalization
  handler: elmos_fde_delivery.handlers.assessment:execute_issue_ontology_and_finding_normalization
  dependencies:
  - static-dynamic-evidence-fusion
  - support-profile-and-unknown-register
  effect_boundary: E3
  routable: false
---

# elmos-fde-issue-ontology-and-finding-normalization

This skill provides the repository-owned bounded implementation for `issue-ontology-and-finding-normalization` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
