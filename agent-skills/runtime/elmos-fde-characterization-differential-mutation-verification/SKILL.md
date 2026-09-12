---
name: elmos-fde-characterization-differential-mutation-verification
description: Repository-owned bounded FDE capability handler for characterization-differential-mutation-verification; external evidence remains NOT_RUN.
metadata:
  package: elmos-fde-autonomous-delivery-repository-refactoring-skills
  version: 5.2.0
  pack: 06-verification-release-operations
  source_id: characterization-differential-mutation-verification
  alias: elmos-fde-characterization-differential-mutation-verification
  handler: elmos_fde_delivery.handlers.operations:execute_characterization_differential_mutation_verification
  dependencies:
  - proof-guided-atomic-refactor-execution
  - business-invariant-recovery
  effect_boundary: E3
  routable: false
---

# elmos-fde-characterization-differential-mutation-verification

This skill provides the repository-owned bounded implementation for `characterization-differential-mutation-verification` in pack `06-verification-release-operations`.

- **Effect Boundary**: E3 (Standalone verification, no production writes)
- **Routable**: false (Invoked via FDE delivery plan or workflow)
- **External Evidence**: `NOT_RUN`
- **Certification**: `NOT_CERTIFIED` (Independent external verification required for E4/E5)
