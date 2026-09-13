---
name: pilot-scope-sow-acceptance
description: Repository-owned bounded FDE capability handler for pilot-scope-sow-acceptance; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 01-fde-engagement
  source_id: pilot-scope-sow-acceptance
  alias: pilot-scope-sow-acceptance
  handler: elmos_fde_delivery.handlers.engagement:execute_pilot_scope_sow_acceptance
  dependencies:
  - stakeholder-workflow-discovery
  - business-baseline-roi
  effect_boundary: E3
  routable: false
---

# pilot-scope-sow-acceptance

This skill provides the repository-owned bounded implementation for `pilot-scope-sow-acceptance` in pack `01-fde-engagement`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
