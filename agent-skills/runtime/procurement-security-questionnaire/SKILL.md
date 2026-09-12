---
name: procurement-security-questionnaire
description: Repository-owned bounded FDE capability handler for procurement-security-questionnaire; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 01-fde-engagement
  source_id: procurement-security-questionnaire
  alias: procurement-security-questionnaire
  handler: elmos_fde_delivery.handlers.engagement:execute_procurement_security_questionnaire
  dependencies:
  - status-risk-decision-communications
  effect_boundary: E3
  routable: false
---

# procurement-security-questionnaire

This skill provides the repository-owned bounded implementation for `procurement-security-questionnaire` in pack `01-fde-engagement`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
