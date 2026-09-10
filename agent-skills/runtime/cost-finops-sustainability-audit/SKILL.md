---
name: cost-finops-sustainability-audit
description: Repository-owned bounded FDE capability handler for cost-finops-sustainability-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: cost-finops-sustainability-audit
  alias: cost-finops-sustainability-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_cost_finops_sustainability_audit
  dependencies:
  - status-risk-decision-communications
  - performance-reliability-observability-audit
  effect_boundary: E3
  routable: false
---

# cost-finops-sustainability-audit

This skill provides the repository-owned bounded implementation for `cost-finops-sustainability-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
