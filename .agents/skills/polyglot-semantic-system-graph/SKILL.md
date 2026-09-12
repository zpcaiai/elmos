---
name: polyglot-semantic-system-graph
description: Repository-owned bounded FDE capability handler for polyglot-semantic-system-graph; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 03-semantic-intelligence
  source_id: polyglot-semantic-system-graph
  alias: polyglot-semantic-system-graph
  handler: elmos_fde_delivery.handlers.semantic:execute_polyglot_semantic_system_graph
  dependencies:
  - reproducible-build-environment
  - support-profile-and-unknown-register
  effect_boundary: E3
  routable: false
---

# polyglot-semantic-system-graph

This skill provides the repository-owned bounded implementation for `polyglot-semantic-system-graph` in pack `03-semantic-intelligence`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
