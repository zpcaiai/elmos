---
name: elmos-fde-root-cause-risk-prioritization
description: Repository-owned bounded FDE capability handler for root-cause-risk-prioritization; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: root-cause-risk-prioritization
  alias: elmos-fde-root-cause-risk-prioritization
  handler: elmos_fde_delivery.handlers.transformation:execute_root_cause_risk_prioritization
  dependencies:
  - architecture-maintainability-audit
  - correctness-concurrency-consistency-audit
  - security-privacy-supply-chain-audit
  - data-database-migration-audit
  - performance-reliability-observability-audit
  effect_boundary: E3
  routable: false
---

# elmos-fde-root-cause-risk-prioritization

This skill provides the repository-owned bounded implementation for `root-cause-risk-prioritization` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
