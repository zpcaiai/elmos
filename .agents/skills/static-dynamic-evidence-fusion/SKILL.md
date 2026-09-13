---
name: static-dynamic-evidence-fusion
description: Repository-owned bounded FDE capability handler for static-dynamic-evidence-fusion; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 03-semantic-intelligence
  source_id: static-dynamic-evidence-fusion
  alias: static-dynamic-evidence-fusion
  handler: elmos_fde_delivery.handlers.semantic:execute_static_dynamic_evidence_fusion
  dependencies:
  - polyglot-semantic-system-graph
  - runtime-observation-and-traffic-capture
  - git-history-ownership-change-coupling
  effect_boundary: E3
  routable: false
---

# static-dynamic-evidence-fusion

This skill provides the repository-owned bounded implementation for `static-dynamic-evidence-fusion` in pack `03-semantic-intelligence`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
