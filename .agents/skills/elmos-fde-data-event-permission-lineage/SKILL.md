---
name: elmos-fde-data-event-permission-lineage
description: Repository-owned bounded FDE capability handler for data-event-permission-lineage; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 03-semantic-intelligence
  source_id: data-event-permission-lineage
  alias: elmos-fde-data-event-permission-lineage
  handler: elmos_fde_delivery.handlers.semantic:execute_data_event_permission_lineage
  dependencies:
  - polyglot-semantic-system-graph
  effect_boundary: E3
  routable: false
---

# elmos-fde-data-event-permission-lineage

This skill provides the repository-owned bounded implementation for `data-event-permission-lineage` in pack `03-semantic-intelligence`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
