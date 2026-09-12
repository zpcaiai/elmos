---
name: asset-inventory-and-classification
description: Repository-owned bounded FDE capability handler for asset-inventory-and-classification; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 02-repository-intake-runtime
  source_id: asset-inventory-and-classification
  alias: asset-inventory-and-classification
  handler: elmos_fde_delivery.handlers.intake:execute_asset_inventory_and_classification
  dependencies:
  - repository-custody-and-revisionset
  effect_boundary: E3
  routable: false
---

# asset-inventory-and-classification

This skill provides the repository-owned bounded implementation for `asset-inventory-and-classification` in pack `02-repository-intake-runtime`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
