---
name: external-dependency-stub-and-service-virtualization
description: Repository-owned bounded FDE capability handler for external-dependency-stub-and-service-virtualization; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 02-repository-intake-runtime
  source_id: external-dependency-stub-and-service-virtualization
  alias: external-dependency-stub-and-service-virtualization
  handler: elmos_fde_delivery.handlers.intake:execute_external_dependency_stub_and_service_virtualization
  dependencies:
  - reproducible-build-environment
  effect_boundary: E3
  routable: false
---

# external-dependency-stub-and-service-virtualization

This skill provides the repository-owned bounded implementation for `external-dependency-stub-and-service-virtualization` in pack `02-repository-intake-runtime`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
