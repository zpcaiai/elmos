---
name: stakeholder-workflow-discovery
description: Repository-owned bounded FDE capability handler for stakeholder-workflow-discovery; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 01-fde-engagement
  source_id: stakeholder-workflow-discovery
  alias: stakeholder-workflow-discovery
  handler: elmos_fde_delivery.handlers.engagement:execute_stakeholder_workflow_discovery
  dependencies:
  []
  effect_boundary: E3
  routable: false
---

# stakeholder-workflow-discovery

This skill provides the repository-owned bounded implementation for `stakeholder-workflow-discovery` in pack `01-fde-engagement`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
