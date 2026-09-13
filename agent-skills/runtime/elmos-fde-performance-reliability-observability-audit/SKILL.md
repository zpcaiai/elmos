---
name: elmos-fde-performance-reliability-observability-audit
description: Repository-owned bounded FDE capability handler for performance-reliability-observability-audit; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 04-unified-assessment
  source_id: performance-reliability-observability-audit
  alias: elmos-fde-performance-reliability-observability-audit
  handler: elmos_fde_delivery.handlers.assessment:execute_performance_reliability_observability_audit
  dependencies:
  - issue-ontology-and-finding-normalization
  - runtime-observation-and-traffic-capture
  effect_boundary: E3
  routable: false
---

# elmos-fde-performance-reliability-observability-audit

This skill provides the repository-owned bounded implementation for `performance-reliability-observability-audit` in pack `04-unified-assessment`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
