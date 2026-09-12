---
name: ux-accessibility-i18n-audit
description: Repository-owned bounded FDE capability handler for ux-accessibility-i18n-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: ux-accessibility-i18n-audit
  alias: ux-accessibility-i18n-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_ux_accessibility_i18n_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - business-capability-code-mapping
  effect_boundary: E3
  routable: false
---

# ux-accessibility-i18n-audit

This skill provides the repository-owned bounded implementation for `ux-accessibility-i18n-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
