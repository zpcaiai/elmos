---
name: security-privacy-supply-chain-audit
description: Repository-owned bounded FDE capability handler for security-privacy-supply-chain-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: security-privacy-supply-chain-audit
  alias: security-privacy-supply-chain-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_security_privacy_supply_chain_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - data-event-permission-lineage
  - reproducible-build-environment
  effect_boundary: E3
  routable: false
---

# security-privacy-supply-chain-audit

This skill provides the repository-owned bounded implementation for `security-privacy-supply-chain-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
