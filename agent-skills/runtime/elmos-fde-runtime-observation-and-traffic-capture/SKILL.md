---
name: elmos-fde-runtime-observation-and-traffic-capture
description: Repository-owned bounded FDE capability handler for runtime-observation-and-traffic-capture; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 02-repository-intake-runtime
  source_id: runtime-observation-and-traffic-capture
  alias: elmos-fde-runtime-observation-and-traffic-capture
  handler: elmos_fde_delivery.handlers.intake:execute_runtime_observation_and_traffic_capture
  dependencies:
  - reproducible-build-environment
  effect_boundary: E3
  routable: false
---

# elmos-fde-runtime-observation-and-traffic-capture

This skill provides the repository-owned bounded implementation for `runtime-observation-and-traffic-capture` in pack `02-repository-intake-runtime`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
