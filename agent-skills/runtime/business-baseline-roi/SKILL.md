---
name: business-baseline-roi
description: Repository-owned bounded FDE capability handler for business-baseline-roi; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 01-fde-engagement
  source_id: business-baseline-roi
  alias: business-baseline-roi
  handler: elmos_fde_delivery.handlers.engagement:execute_business_baseline_roi
  dependencies:
  - stakeholder-workflow-discovery
  effect_boundary: E3
  routable: false
---

# business-baseline-roi

This skill provides the repository-owned bounded implementation for `business-baseline-roi` in pack `01-fde-engagement`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
