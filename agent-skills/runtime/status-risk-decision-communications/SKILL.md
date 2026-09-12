---
name: status-risk-decision-communications
description: Repository-owned bounded FDE capability handler for status-risk-decision-communications; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 01-fde-engagement
  source_id: status-risk-decision-communications
  alias: status-risk-decision-communications
  handler: elmos_fde_delivery.handlers.engagement:execute_status_risk_decision_communications
  dependencies:
  - pilot-scope-sow-acceptance
  effect_boundary: E3
  routable: false
---

# status-risk-decision-communications

This skill provides the repository-owned bounded implementation for `status-risk-decision-communications` in pack `01-fde-engagement`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
