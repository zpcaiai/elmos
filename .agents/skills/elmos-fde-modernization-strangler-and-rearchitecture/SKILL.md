---
name: elmos-fde-modernization-strangler-and-rearchitecture
description: Repository-owned bounded FDE capability handler for modernization-strangler-and-rearchitecture; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 05-planning-transformation
  source_id: modernization-strangler-and-rearchitecture
  alias: elmos-fde-modernization-strangler-and-rearchitecture
  handler: elmos_fde_delivery.handlers.transformation:execute_modernization_strangler_and_rearchitecture
  dependencies:
  - proof-guided-atomic-refactor-execution
  - target-architecture-alternatives-and-adr
  effect_boundary: E3
  routable: false
---

# elmos-fde-modernization-strangler-and-rearchitecture

This skill provides the repository-owned bounded implementation for `modernization-strangler-and-rearchitecture` in pack `05-planning-transformation`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
