---
name: elmos-fde-business-invariant-recovery
description: Repository-owned bounded FDE capability handler for business-invariant-recovery; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: business-invariant-recovery
  alias: elmos-fde-business-invariant-recovery
  handler: elmos_fde_delivery.handlers.transformation:execute_business_invariant_recovery
  dependencies:
  - business-capability-code-mapping
  - root-cause-risk-prioritization
  effect_boundary: E3
  routable: false
---

# elmos-fde-business-invariant-recovery

This skill provides the repository-owned bounded implementation for `business-invariant-recovery` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
