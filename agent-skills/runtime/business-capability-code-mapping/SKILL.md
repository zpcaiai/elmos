---
name: business-capability-code-mapping
description: Repository-owned bounded FDE capability handler for business-capability-code-mapping; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 03-semantic-intelligence
  source_id: business-capability-code-mapping
  alias: business-capability-code-mapping
  handler: elmos_fde_delivery.handlers.semantic:execute_business_capability_code_mapping
  dependencies:
  - stakeholder-workflow-discovery
  - polyglot-semantic-system-graph
  effect_boundary: E3
  routable: false
---

# business-capability-code-mapping

This skill provides the repository-owned bounded implementation for `business-capability-code-mapping` in pack `03-semantic-intelligence`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
