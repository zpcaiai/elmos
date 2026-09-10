---
name: formal-assurance-routing
description: Repository-owned bounded FDE capability handler for formal-assurance-routing; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 06-verification-release-operations
  source_id: formal-assurance-routing
  alias: formal-assurance-routing
  handler: elmos_fde_delivery.handlers.operations:execute_formal_assurance_routing
  dependencies:
  - business-invariant-recovery
  - correctness-concurrency-consistency-audit
  effect_boundary: E3
  routable: false
---

# formal-assurance-routing

This skill provides the repository-owned bounded implementation for `formal-assurance-routing` in pack `06-verification-release-operations`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
