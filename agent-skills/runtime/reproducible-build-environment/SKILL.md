---
name: reproducible-build-environment
description: Repository-owned bounded FDE capability handler for reproducible-build-environment; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 02-repository-intake-runtime
  source_id: reproducible-build-environment
  alias: reproducible-build-environment
  handler: elmos_fde_delivery.handlers.intake:execute_reproducible_build_environment
  dependencies:
  - asset-inventory-and-classification
  effect_boundary: E3
  routable: false
---

# reproducible-build-environment

This skill provides the repository-owned bounded implementation for `reproducible-build-environment` in pack `02-repository-intake-runtime`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
